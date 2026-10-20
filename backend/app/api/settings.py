from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import require_owner
from app.connectors.google_auth import GoogleApiClient, GoogleApiError
from app.connectors.google_properties import list_google_properties
from app.db import get_db
from app.models.connection import GoogleConnection
from app.schemas.metrics import ReportingSettings, ReportingSettingsUpdate
from app.connectors.site_crawler import validate_site_url
from app.services.event_mapping import save_event_mapping
from app.services.property_selection import validate_property_selection


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/reporting", response_model=ReportingSettings)
def get_reporting_settings(
    db: Session = Depends(get_db),
    _: str = Depends(require_owner),
) -> ReportingSettings:
    connection = db.get(GoogleConnection, 1)
    if connection is None:
        return ReportingSettings()
    return ReportingSettings(
        site_url=connection.site_url,
        search_console_site=connection.search_console_site,
        ga4_property_id=connection.ga4_property_id,
        cta_event=connection.cta_event,
        invite_submit_event=connection.invite_submit_event,
    )


@router.put("/reporting", response_model=ReportingSettings)
def put_reporting_settings(
    payload: ReportingSettingsUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_owner),
) -> ReportingSettings:
    connection = db.get(GoogleConnection, 1)
    if connection is None:
        raise HTTPException(status_code=400, detail="Connect Google before changing reporting settings")
    if (payload.cta_event or payload.invite_submit_event) and not payload.ga4_property_id:
        raise HTTPException(status_code=400, detail="Select a GA4 property before mapping events")
    if payload.search_console_site or payload.ga4_property_id:
        try:
            accessible = list_google_properties(GoogleApiClient(db))
        except GoogleApiError as exc:
            status = 401 if exc.code in {"not_connected", "reconnect_required"} else 502
            raise HTTPException(status_code=status, detail=exc.message) from exc
        validate_property_selection(accessible, payload.search_console_site, payload.ga4_property_id)

    try:
        connection.site_url = validate_site_url(payload.site_url) if payload.site_url else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    connection.search_console_site = payload.search_console_site
    connection.ga4_property_id = payload.ga4_property_id
    try:
        return save_event_mapping(db, payload.cta_event, payload.invite_submit_event)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
