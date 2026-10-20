from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-only-session-signing-key")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://testserver/api/auth/google/callback")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, class_=Session)

    def override_db() -> Iterator[Session]:
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_non_owner_cannot_start_session(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth

    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "refresh"})
    monkeypatch.setattr(auth, "verify_id_token", lambda token, nonce: {"email": "stranger@example.com", "email_verified": True, "nonce": nonce, "iss": "https://accounts.google.com", "aud": "test-client-id"})
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]

    response = client.get(f"/api/auth/google/callback?code=code&state={state}")

    assert response.status_code == 403
    assert "session" not in response.cookies


def test_oauth_state_mismatch_is_rejected(client: TestClient) -> None:
    response = client.get("/api/auth/google/start")

    callback = client.get("/api/auth/google/callback?code=code&state=wrong")

    assert response.status_code == 200
    assert callback.status_code == 400


def test_oauth_nonce_and_issuer_are_validated(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth

    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "refresh"})
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": "wrong-nonce", "iss": "https://accounts.google.com", "aud": "test-client-id"})
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]

    nonce_callback = client.get(f"/api/auth/google/callback?code=code&state={state}", follow_redirects=False)

    assert nonce_callback.status_code == 400

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": "", "iss": "https://attacker.example", "aud": "test-client-id"})
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]
    issuer_callback = client.get(f"/api/auth/google/callback?code=code&state={state}", follow_redirects=False)

    assert issuer_callback.status_code == 400


def test_session_required_for_private_routes(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_session_signature_and_owner_allowlist_are_enforced(client: TestClient) -> None:
    from app.core.auth import make_session

    client.cookies.set("owner_session", make_session("owner@example.com", "test-only-session-signing-key"))
    assert client.get("/api/auth/me").json() == {"email": "owner@example.com"}

    client.cookies.set("owner_session", make_session("stranger@example.com", "test-only-session-signing-key"))
    assert client.get("/api/auth/me").status_code == 401

    client.cookies.set("owner_session", "tampered.invalid")
    assert client.get("/api/auth/me").status_code == 401


def test_expired_refresh_token_requires_reconnect() -> None:
    from app.connectors.google_auth import is_reconnect_required

    assert is_reconnect_required({"error": "invalid_grant"}) is True


def test_token_is_not_returned_by_connection_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth

    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "secret-refresh-token"})
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": client.cookies.get("oauth_nonce"), "iss": "https://accounts.google.com", "aud": "test-client-id"})
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]
    callback = client.get(f"/api/auth/google/callback?code=code&state={state}", follow_redirects=False)

    status = client.get("/api/connections/google")

    assert callback.status_code == 303
    assert status.status_code == 200
    assert status.json() == {"connected": True, "reconnect_required": False, "search_console_site": None, "ga4_property_id": None}
    assert "secret-refresh-token" not in status.text


def test_production_owner_session_cookie_is_secure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "secret-refresh-token"})
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": client.cookies.get("oauth_nonce"), "iss": "https://accounts.google.com", "aud": "test-client-id"})
    start = client.get("https://testserver/api/auth/google/start")
    callback = client.get(f"https://testserver/api/auth/google/callback?code=code&state={start.cookies['oauth_state']}", follow_redirects=False)

    assert callback.status_code == 303, callback.text
    session_cookie = next(value for value in callback.headers.get_list("set-cookie") if value.startswith("owner_session="))
    assert "secure" in session_cookie.casefold()
    assert "httponly" in session_cookie.casefold()


def test_disconnect_revokes_and_removes_google_credentials(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth, connections

    revoked: list[str] = []

    class RevokeResponse:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "secret-refresh-token"})
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": client.cookies.get("oauth_nonce"), "iss": "https://accounts.google.com", "aud": "test-client-id"})
    monkeypatch.setattr(connections.httpx, "post", lambda url, data, timeout: (revoked.append(data["token"]) or RevokeResponse()))
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]
    client.get(f"/api/auth/google/callback?code=code&state={state}", follow_redirects=False)

    response = client.delete("/api/connections/google")

    assert response.status_code == 204
    assert revoked == ["secret-refresh-token"]
    assert client.get("/api/connections/google").json() == {"connected": False, "reconnect_required": False, "search_console_site": None, "ga4_property_id": None}


def test_google_property_selection_is_access_checked_and_persisted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth
    from app.connectors.google_auth import GoogleApiClient

    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "secret-refresh-token"})
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": client.cookies.get("oauth_nonce"), "iss": "https://accounts.google.com", "aud": "test-client-id"})
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]
    client.get(f"/api/auth/google/callback?code=code&state={state}", follow_redirects=False)

    def properties(self: GoogleApiClient, method: str, url: str, **kwargs: object) -> dict[str, object]:
        if "webmasters/v3/sites" in url:
            return {"siteEntry": [{"siteUrl": "sc-domain:sparestracker.com", "permissionLevel": "siteOwner"}]}
        return {"accountSummaries": [{"displayName": "Sparestracker", "propertySummaries": [{"property": "properties/123456789", "displayName": "Sparestracker GA4"}]}]}

    monkeypatch.setattr(GoogleApiClient, "request_json", properties)
    response = client.put("/api/connections/google/selection", json={"search_console_site": "sc-domain:sparestracker.com", "ga4_property_id": "123456789"})

    assert response.status_code == 200
    assert response.json() == {"search_console_site": "sc-domain:sparestracker.com", "ga4_property_id": "123456789"}
    assert client.get("/api/connections/google").json()["ga4_property_id"] == "123456789"

    invalid = client.put("/api/connections/google/selection", json={"search_console_site": "https://attacker.example/", "ga4_property_id": None})
    assert invalid.status_code == 400


def test_reporting_settings_update_properties_and_event_mappings(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import auth
    from app.connectors.google_auth import GoogleApiClient

    monkeypatch.setattr(auth, "exchange_code", lambda code: {"id_token": "mock-id-token", "refresh_token": "secret-refresh-token"})
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda token, request, audience: {"email": "owner@example.com", "email_verified": True, "nonce": client.cookies.get("oauth_nonce"), "iss": "https://accounts.google.com", "aud": "test-client-id"})
    start = client.get("/api/auth/google/start")
    state = start.cookies["oauth_state"]
    client.get(f"/api/auth/google/callback?code=code&state={state}", follow_redirects=False)

    def properties(self: GoogleApiClient, method: str, url: str, **kwargs: object) -> dict[str, object]:
        if "webmasters/v3/sites" in url:
            return {"siteEntry": [{"siteUrl": "sc-domain:sparestracker.com", "permissionLevel": "siteOwner"}]}
        return {"accountSummaries": [{"displayName": "Sparestracker", "propertySummaries": [{"property": "properties/123456789", "displayName": "Sparestracker GA4"}]}]}

    monkeypatch.setattr(GoogleApiClient, "request_json", properties)
    response = client.put("/api/settings/reporting", json={
        "site_url": "https://sparestracker.com/",
        "search_console_site": "sc-domain:sparestracker.com",
        "ga4_property_id": "123456789",
        "cta_event": "cta_click",
        "invite_submit_event": "invite_submit",
    })

    assert response.status_code == 200
    assert response.json() == {
        "site_url": "https://sparestracker.com/",
        "search_console_site": "sc-domain:sparestracker.com",
        "ga4_property_id": "123456789",
        "cta_event": "cta_click",
        "invite_submit_event": "invite_submit",
    }
    assert client.get("/api/settings/reporting").json() == response.json()

    unsafe_site = client.put("/api/settings/reporting", json={
        "site_url": "http://127.0.0.1/admin",
        "search_console_site": None,
        "ga4_property_id": None,
        "cta_event": None,
        "invite_submit_event": None,
    })
    assert unsafe_site.status_code == 400

    unverified = client.put("/api/settings/reporting", json={
        "search_console_site": "https://other.example/",
        "ga4_property_id": "123456789",
        "cta_event": "cta_click",
        "invite_submit_event": "invite_submit",
    })
    assert unverified.status_code == 400
