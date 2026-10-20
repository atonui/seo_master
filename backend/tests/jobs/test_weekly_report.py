from datetime import date

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.db import Base
from app.models.report import SavedReport
from app.services import report_runner
from app.jobs import weekly_report


def test_weekly_job_uses_completed_nairobi_monday_to_sunday():
    assert weekly_report.completed_week(date(2026, 10, 19)) == (date(2026, 10, 12), date(2026, 10, 18))


def test_duplicate_weekly_job_is_idempotent_and_closes_database(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = []
    closed = []
    def session_factory():
        session = Session(engine)
        sessions.append(session)
        original_close = session.close
        def close():
            closed.append(True)
            original_close()
        session.close = close
        return session
    monkeypatch.setattr(weekly_report, "SessionLocal", session_factory)
    monkeypatch.setattr(weekly_report, "completed_week", lambda: (date(2026, 10, 12), date(2026, 10, 18)))
    runs = []
    def fake_run(session, start, end):
        runs.append((start, end))
        session.add(SavedReport(start_date=start, end_date=end, status="ready", finding_count=0, source_timestamps={}, data={}))
        session.commit()
    monkeypatch.setattr(weekly_report, "run_report", fake_run)
    assert weekly_report.run_weekly_report() == 0
    assert weekly_report.run_weekly_report() == 0
    assert len(runs) == 1
    assert len(closed) == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SavedReport)) == 1
    engine.dispose()


def test_job_returns_failure_and_closes_session(monkeypatch):
    class FakeSession:
        closed = False
        def scalar(self, query): return None
        def rollback(self): pass
        def close(self): self.closed = True
    session = FakeSession()
    monkeypatch.setattr(weekly_report, "SessionLocal", lambda: session)
    monkeypatch.setattr(weekly_report, "completed_week", lambda: (date(2026, 10, 12), date(2026, 10, 18)))
    monkeypatch.setattr(weekly_report, "run_report", lambda *args: (_ for _ in ()).throw(report_runner.ReportRunError("failure")))
    assert weekly_report.run_weekly_report() == 1
    assert session.closed
