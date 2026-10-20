from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.connectors import google_auth
from app.db import Base
from app.models.connection import GoogleConnection
from app.models.report import SavedReport
from app.schemas.google import ConnectorResult
from app.services import report_runner


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_equal_date_windows_and_report_persistence(db, monkeypatch):
    stamp = datetime.now(timezone.utc)
    db.add(GoogleConnection(id=1, owner_email="owner@example.com", encrypted_credentials="x", search_console_site="sc-domain:sparestracker.com"))
    db.commit()
    monkeypatch.setattr(report_runner, "GoogleApiClient", lambda db: object())
    calls = []
    def fake_query(api, site, start, end):
        calls.append((start, end))
        return ConnectorResult(data=[], retrieved_at=stamp, complete=True)
    monkeypatch.setattr(report_runner, "query_search_performance", fake_query)
    detail = report_runner.run_report(db, date(2026, 9, 1), date(2026, 9, 28))
    assert detail.date_range == "2026-09-01 to 2026-09-28"
    assert db.scalar(select(func.count()).select_from(SavedReport)) == 1
    row = db.get(SavedReport, detail.id)
    assert row.start_date == date(2026, 9, 1)
    assert row.end_date == date(2026, 9, 28)
    assert calls == [(date(2026, 9, 1), date(2026, 9, 28)), (date(2026, 8, 4), date(2026, 8, 31))]
    assert detail.funnel.status == "setup_needed"


def test_failed_sync_preserves_last_good_report(db, monkeypatch):
    db.add(GoogleConnection(id=1, owner_email="owner@example.com", encrypted_credentials="x", search_console_site="sc-domain:sparestracker.com"))
    db.add(SavedReport(start_date=date(2026, 8, 1), end_date=date(2026, 8, 28), status="ready", finding_count=0, source_timestamps={}, data={}))
    db.commit()
    monkeypatch.setattr(report_runner, "GoogleApiClient", lambda db: object())
    monkeypatch.setattr(report_runner, "query_search_performance", lambda *args: (_ for _ in ()).throw(google_auth.GoogleApiError("timeout", "Google timed out")))
    with pytest.raises(report_runner.ReportRunError):
        report_runner.run_report(db, date(2026, 9, 1), date(2026, 9, 28))
    assert db.scalar(select(func.count()).select_from(SavedReport)) == 1


def test_reconnect_required_stops_before_sync(db):
    db.add(GoogleConnection(id=1, owner_email="owner@example.com", encrypted_credentials="x", reconnect_required=True, search_console_site="sc-domain:sparestracker.com"))
    db.commit()
    with pytest.raises(report_runner.ReportRunError, match="reconnect"):
        report_runner.run_report(db, date(2026, 9, 1), date(2026, 9, 28))
