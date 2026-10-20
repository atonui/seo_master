from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import SessionLocal
from app.core.config import get_settings
from app.core.deployment import validate_production_settings
from app.models.report import SavedReport
from app.services.report_runner import ReportRunError, run_report


NAIROBI = ZoneInfo("Africa/Nairobi")


def completed_week(today: date | None = None) -> tuple[date, date]:
    local_today = today or datetime.now(NAIROBI).date()
    this_monday = local_today - timedelta(days=local_today.weekday())
    end = this_monday - timedelta(days=1)
    start = end - timedelta(days=6)
    return start, end


def run_weekly_report() -> int:
    validate_production_settings(get_settings())
    db = SessionLocal()
    try:
        start, end = completed_week()
        existing = db.scalar(select(SavedReport).where(SavedReport.start_date == start, SavedReport.end_date == end))
        if existing is not None and existing.status == "ready":
            return 0
        run_report(db, start, end)
        return 0
    except (ReportRunError, ValueError):
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run_weekly_report())
