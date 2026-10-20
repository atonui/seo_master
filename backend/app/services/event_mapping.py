from sqlalchemy.orm import Session

from app.models.connection import GoogleConnection
from app.schemas.google import GA4Row
from app.schemas.metrics import FunnelEventSummary, ReportingSettings


def _clean_event_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = value.strip()
    if not name:
        return None
    if len(name) > 100 or any(ord(character) < 32 for character in name):
        raise ValueError("Event names must be printable and no longer than 100 characters")
    return name


def save_event_mapping(
    db: Session,
    cta_event: str | None,
    invite_submit_event: str | None,
) -> ReportingSettings:
    connection = db.get(GoogleConnection, 1)
    if connection is None:
        raise ValueError("Connect Google before configuring GA4 events")
    connection.cta_event = _clean_event_name(cta_event)
    connection.invite_submit_event = _clean_event_name(invite_submit_event)
    db.commit()
    return ReportingSettings(
        site_url=connection.site_url,
        search_console_site=connection.search_console_site,
        ga4_property_id=connection.ga4_property_id,
        cta_event=connection.cta_event,
        invite_submit_event=connection.invite_submit_event,
    )


def map_funnel_events(
    rows: list[GA4Row],
    settings: ReportingSettings,
    *,
    complete: bool = True,
) -> FunnelEventSummary:
    if not complete:
        return FunnelEventSummary(
            cta_clicks=None,
            invite_submissions=None,
            status="incomplete",
            warning="GA4 event data is incomplete; funnel counts are not shown as current.",
        )
    if not settings.invite_submit_event:
        cta_count = (
            sum(row.event_count for row in rows if row.event_name == settings.cta_event)
            if settings.cta_event
            else None
        )
        return FunnelEventSummary(
            cta_clicks=cta_count,
            invite_submissions=None,
            status="setup_needed",
            warning="Map the invitation submission event before reporting conversion counts.",
        )
    return FunnelEventSummary(
        cta_clicks=(
            sum(row.event_count for row in rows if row.event_name == settings.cta_event)
            if settings.cta_event
            else None
        ),
        invite_submissions=sum(row.event_count for row in rows if row.event_name == settings.invite_submit_event),
        status="ready",
    )
