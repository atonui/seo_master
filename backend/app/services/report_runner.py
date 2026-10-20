from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.ga4 import query_ga4
from app.connectors.google_auth import GoogleApiClient, GoogleApiError
from app.connectors.search_console import query_search_performance
from app.connectors.site_crawler import crawl_site
from app.models.connection import GoogleConnection
from app.models.report import SavedReport
from app.schemas.google import GA4Row, SearchRow
from app.schemas.metrics import MetricPoint, ReportingSettings
from app.schemas.recommendation import Finding, Recommendation
from app.schemas.report import ReportDetail
from app.services.metric_comparison import compare_periods
from app.services.metric_normalization import normalize_metrics
from app.services.event_mapping import map_funnel_events
from app.services.recommendation_generator import generate_recommendations
from app.services.analysis import analyze_report


class ReportRunError(RuntimeError):
    pass


def default_report_window(today: date | None = None) -> tuple[date, date]:
    # Use a conservative three day lag for GA4 and Search Console processing.
    end = (today or date.today()) - timedelta(days=3)
    return end - timedelta(days=27), end


def _range_label(start: date, end: date) -> str:
    return f"{start.isoformat()} to {end.isoformat()}"


def _persist(db: Session, start: date, end: date, status: str, metrics: list[MetricPoint], comparison, findings: list[Finding], recommendations: list[Recommendation], timestamps: dict[str, datetime], warning: str | None, funnel=None) -> SavedReport:
    row = SavedReport(start_date=start, end_date=end, status=status, finding_count=len(findings), source_timestamps={key: value.isoformat() for key, value in timestamps.items()}, warning=warning, data={
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "comparison": [item.model_dump(mode="json") for item in comparison],
        "findings": [item.model_dump(mode="json") for item in findings],
        "recommendations": [item.model_dump(mode="json") for item in recommendations],
        "funnel": funnel.model_dump(mode="json") if funnel else None,
    })
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def run_report(db: Session, start_date: date | None = None, end_date: date | None = None) -> ReportDetail:
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date and end_date must be supplied together")
    if start_date is None:
        start_date, end_date = default_report_window()
    assert end_date is not None
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    days = (end_date - start_date).days + 1
    previous_start = start_date - timedelta(days=days)
    previous_end = start_date - timedelta(days=1)
    connection = db.get(GoogleConnection, 1)
    if connection is None:
        raise ReportRunError("Connect the owner Google account first")
    if connection.reconnect_required:
        raise ReportRunError("Google authorization expired; reconnect the account")
    reporting = ReportingSettings(site_url=connection.site_url, search_console_site=connection.search_console_site, ga4_property_id=connection.ga4_property_id, cta_event=connection.cta_event, invite_submit_event=connection.invite_submit_event)
    if not (reporting.search_console_site or reporting.ga4_property_id or reporting.site_url):
        raise ReportRunError("Choose at least one report source or website domain in reporting settings")

    api = GoogleApiClient(db)
    warnings: list[str] = []
    timestamps: dict[str, datetime] = {}
    failed_sources_without_data: list[str] = []
    search_current: list[SearchRow] = []
    search_previous: list[SearchRow] = []
    ga_current: list[GA4Row] = []
    ga_previous: list[GA4Row] = []
    search_current_complete = search_previous_complete = not reporting.search_console_site
    ga_current_complete = ga_previous_complete = not reporting.ga4_property_id
    try:
        if reporting.search_console_site:
            current = query_search_performance(api, reporting.search_console_site, start_date, end_date)
            previous = query_search_performance(api, reporting.search_console_site, previous_start, previous_end)
            search_current, search_previous = current.data, previous.data
            search_current_complete, search_previous_complete = current.complete, previous.complete
            timestamps["search_console"] = current.retrieved_at
            if not current.complete or not previous.complete:
                warnings.extend(filter(None, [current.warning, previous.warning, "Search Console data is incomplete."]))
                if not current.complete and not current.data:
                    failed_sources_without_data.append("search_console")
        if reporting.ga4_property_id:
            events = [name for name in (reporting.cta_event, reporting.invite_submit_event) if name]
            current = query_ga4(api, reporting.ga4_property_id, start_date, end_date, events)
            previous = query_ga4(api, reporting.ga4_property_id, previous_start, previous_end, events)
            ga_current, ga_previous = current.data, previous.data
            ga_current_complete, ga_previous_complete = current.complete, previous.complete
            timestamps["ga4"] = current.retrieved_at
            if not current.complete or not previous.complete:
                warnings.extend(filter(None, [current.warning, previous.warning, "GA4 data is incomplete."]))
                if not current.complete and not current.data:
                    failed_sources_without_data.append("ga4")
    except GoogleApiError as exc:
        raise ReportRunError(exc.message) from exc

    crawl = None
    if reporting.site_url:
        crawl = crawl_site(reporting.site_url)
        timestamps["website_crawl"] = crawl.retrieved_at
        warnings.extend(crawl.warnings)

    if failed_sources_without_data and len(failed_sources_without_data) == sum(bool(value) for value in (reporting.search_console_site, reporting.ga4_property_id)) and not crawl:
        raise ReportRunError("All selected reporting sources returned no data; the previous saved report was kept")

    metrics = normalize_metrics(search_current, ga_current, reporting, start_date, end_date, search_complete=search_current_complete, ga_complete=ga_current_complete)
    previous_metrics = normalize_metrics(search_previous, ga_previous, reporting, previous_start, previous_end, search_complete=search_previous_complete, ga_complete=ga_previous_complete)
    metrics = _selected_source_metrics(metrics, reporting)
    previous_metrics = _selected_source_metrics(previous_metrics, reporting)
    comparison = []
    if metrics and previous_metrics and search_current_complete and search_previous_complete and ga_current_complete and ga_previous_complete:
        comparison = compare_periods(metrics, previous_metrics)
    findings = analyze_report(search_current, ga_current, crawl, reporting) if crawl else analyze_report(search_current, ga_current, _empty_crawl(), reporting)
    try:
        recommendations = generate_recommendations(findings)
    except Exception as exc:
        recommendations = []
        warnings.append(f"Recommendation generation is unavailable ({type(exc).__name__}).")
    unique_warnings = list(dict.fromkeys(warnings))
    funnel = map_funnel_events(ga_current, reporting, complete=ga_current_complete) if reporting.ga4_property_id else map_funnel_events([], reporting)
    row = _persist(db, start_date, end_date, "partial" if unique_warnings else "ready", metrics, comparison, findings, recommendations, timestamps, "; ".join(unique_warnings) or None, funnel)
    return report_detail(row)


def _empty_crawl():
    from app.schemas.audit import CrawlResult
    return CrawlResult(complete=False, retrieved_at=datetime.now(timezone.utc))


def _selected_source_metrics(points: list[MetricPoint], reporting: ReportingSettings) -> list[MetricPoint]:
    search_names = {"clicks", "impressions", "ctr", "average_position"}
    ga_names = {"sessions", "engagement_rate", "cta_clicks", "invite_submissions"}
    return [point for point in points if (reporting.search_console_site or point.metric not in search_names) and (reporting.ga4_property_id or (point.metric not in ga_names and not point.metric.startswith(("landing_sessions:", "source_sessions:", "event_count:"))))]


def report_detail(row: SavedReport) -> ReportDetail:
    data = row.data
    return ReportDetail(
        id=row.id, created_at=row.created_at, date_range=_range_label(row.start_date, row.end_date), status=row.status,
        finding_count=row.finding_count,
        source_timestamps={key: datetime.fromisoformat(value) for key, value in row.source_timestamps.items()},
        warning=row.warning,
        metrics=data.get("metrics", []), comparison=data.get("comparison", []), findings=data.get("findings", []), recommendations=data.get("recommendations", []), funnel=data.get("funnel"),
    )


def report_summary(row: SavedReport):
    from app.schemas.report import ReportSummary
    return ReportSummary(
        id=row.id, created_at=row.created_at, date_range=_range_label(row.start_date, row.end_date), status=row.status,
        finding_count=row.finding_count,
        source_timestamps={key: datetime.fromisoformat(value) for key, value in row.source_timestamps.items()},
        warning=row.warning,
    )


def list_reports(db: Session, limit: int = 20) -> list[SavedReport]:
    rows = db.scalars(select(SavedReport).order_by(SavedReport.created_at.desc()).limit(max(1, min(limit, 100)))).all()
    return list(rows)


def get_report(db: Session, report_id: str) -> ReportDetail | None:
    row = db.get(SavedReport, report_id)
    return report_detail(row) if row else None
