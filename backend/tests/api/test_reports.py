from collections.abc import Iterator
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import SESSION_COOKIE, make_session
from app.db import Base, get_db
from app.main import app
from app.models.connection import GoogleConnection
from app.models.report import SavedReport


@pytest.fixture
def owner_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session]]:
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-only-session-signing-key")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    active: list[Session] = []
    def override_db():
        session = factory()
        active.append(session)
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, make_session("owner@example.com", "test-only-session-signing-key"))
        yield client, factory()
    app.dependency_overrides.clear()
    for session in active:
        session.close()
    engine.dispose()


def seed_report(db: Session) -> SavedReport:
    evidence = {"id": "gsc:q:clicks", "metric": "clicks", "value": 8, "period": "2026-10-01", "source": "Google Search Console", "label": "tractor parts"}
    finding = {"code": "search_low_ctr", "title": "Low CTR", "summary": "Eight clicks.", "source": "Google Search Console", "evidence": [evidence], "limitations": []}
    report = SavedReport(start_date=date(2026, 10, 1), end_date=date(2026, 10, 28), status="ready", finding_count=1, source_timestamps={"search_console": datetime.now(timezone.utc).isoformat()}, data={"metrics": [], "comparison": [], "findings": [finding], "recommendations": []})
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_report_list_get_and_delete(owner_client):
    client, db = owner_client
    row = seed_report(db)
    assert client.get("/api/reports").json()[0]["id"] == row.id
    assert client.get(f"/api/reports/{row.id}").json()["findings"][0]["evidence"][0]["value"] == 8
    assert client.delete(f"/api/reports/{row.id}").status_code == 204
    assert client.get(f"/api/reports/{row.id}").status_code == 404


def test_chat_cannot_cite_evidence_outside_saved_report(owner_client, monkeypatch):
    client, db = owner_client
    row = seed_report(db)
    from app.api import chat
    class Responses:
        def parse(self, **kwargs):
            from app.schemas.chat import ChatDraft
            return type("Response", (), {"output_parsed": ChatDraft(answer="Unsupported", evidence_ids=["invented"])})()
    class MockOpenAI:
        responses = Responses()
    monkeypatch.setattr(chat, "OpenAI", lambda **kwargs: MockOpenAI())
    monkeypatch.setattr(chat, "get_settings", lambda: type("Settings", (), {"openai_api_key": "key", "openai_model": "model"})())
    response = client.post("/api/chat", json={"question": "What happened?", "report_id": row.id})
    assert response.status_code == 502


def test_chat_answer_is_bound_to_retrieved_report_evidence(owner_client, monkeypatch):
    client, db = owner_client
    row = seed_report(db)
    from app.api import chat
    class Responses:
        def parse(self, **kwargs):
            assert "gsc:q:clicks" in kwargs["input"][1]["content"]
            from app.schemas.chat import ChatDraft
            return type("Response", (), {"output_parsed": ChatDraft(answer="The query received 8 clicks.", evidence_ids=["gsc:q:clicks"])})()
    class MockOpenAI:
        responses = Responses()
    monkeypatch.setattr(chat, "OpenAI", lambda **kwargs: MockOpenAI())
    monkeypatch.setattr(chat, "get_settings", lambda: type("Settings", (), {"openai_api_key": "key", "openai_model": "model"})())
    response = client.post("/api/chat", json={"question": "How many clicks?", "report_id": row.id})
    assert response.status_code == 200
    assert response.json()["evidence_ids"] == ["gsc:q:clicks"]


def test_google_disconnect_deletes_saved_reports(owner_client, monkeypatch):
    client, db = owner_client
    seed_report(db)
    db.add(GoogleConnection(id=1, owner_email="owner@example.com", encrypted_credentials="opaque"))
    db.commit()
    from app.api import connections
    monkeypatch.setattr(connections, "decrypt_secret", lambda _: '{"refresh_token":"token"}')
    monkeypatch.setattr(connections.httpx, "post", lambda *args, **kwargs: type("Response", (), {"raise_for_status": lambda self: None})())
    assert client.delete("/api/connections/google").status_code == 204
    assert db.scalar(select(func.count()).select_from(SavedReport)) == 0


def test_reports_require_owner_login(owner_client):
    client, _ = owner_client
    client.cookies.clear()
    assert client.get("/api/reports").status_code == 401
