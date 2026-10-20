import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.connectors import google_auth
from app.core.crypto import encrypt_secret
from app.db import Base
from app.models.connection import GoogleConnection


def test_invalid_grant_marks_saved_connection_for_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(GoogleConnection(
            id=1,
            owner_email="owner@example.com",
            encrypted_credentials=encrypt_secret(json.dumps({"refresh_token": "revoked"})),
        ))
        db.commit()
        monkeypatch.setattr(google_auth, "_refresh_access_token", lambda token: (_ for _ in ()).throw(google_auth.GoogleApiError("reconnect_required", "invalid_grant")))

        with pytest.raises(google_auth.GoogleApiError) as error:
            google_auth.GoogleApiClient(db).get_access_token()

        assert error.value.code == "reconnect_required"
        assert db.get(GoogleConnection, 1).reconnect_required is True
    engine.dispose()


def test_google_request_timeout_is_bounded_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    api = google_auth.GoogleApiClient(db=None)  # type: ignore[arg-type]
    monkeypatch.setattr(api, "get_access_token", lambda: "test-access-token")
    attempts: list[int] = []
    monkeypatch.setattr(google_auth.time, "sleep", lambda seconds: None)

    def timeout(*args: object, **kwargs: object) -> httpx.Response:
        attempts.append(1)
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(google_auth.httpx, "request", timeout)

    with pytest.raises(google_auth.GoogleApiError) as error:
        api.request_json("GET", "https://example.test/report")

    assert error.value.code == "timeout"
    assert len(attempts) == 3


def test_google_request_retries_rate_limit_with_bounded_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    api = google_auth.GoogleApiClient(db=None)  # type: ignore[arg-type]
    monkeypatch.setattr(api, "get_access_token", lambda: "test-access-token")
    delays: list[float] = []
    attempts = [httpx.Response(429, headers={"Retry-After": "9"}, json={"error": "quota"}), httpx.Response(200, json={"ok": True})]
    monkeypatch.setattr(google_auth.time, "sleep", delays.append)
    monkeypatch.setattr(google_auth.httpx, "request", lambda *args, **kwargs: attempts.pop(0))

    assert api.request_json("GET", "https://example.test/report") == {"ok": True}
    assert delays == [2.0]
