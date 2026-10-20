from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.auth import require_owner
from app.db import get_db
from app.models.report import SavedReport
from app.schemas.report import ReportDetail, ReportRunRequest, ReportSummary
from app.services.report_runner import ReportRunError, get_report, list_reports, report_summary, run_report


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/run", response_model=ReportDetail)
def run_report_endpoint(payload: ReportRunRequest, db: Session = Depends(get_db), _: str = Depends(require_owner)) -> ReportDetail:
    try:
        return run_report(db, payload.start_date, payload.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ReportRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[ReportSummary])
def reports_list(limit: int = 20, db: Session = Depends(get_db), _: str = Depends(require_owner)) -> list[ReportSummary]:
    return [report_summary(row) for row in list_reports(db, limit)]


@router.get("/{report_id}", response_model=ReportDetail)
def report_get(report_id: str, db: Session = Depends(get_db), _: str = Depends(require_owner)) -> ReportDetail:
    report = get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.delete("/{report_id}", status_code=204)
def report_delete(report_id: str, db: Session = Depends(get_db), _: str = Depends(require_owner)) -> Response:
    report = db.get(SavedReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return Response(status_code=204)
