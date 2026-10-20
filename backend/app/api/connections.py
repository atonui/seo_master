import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.auth import require_owner
from app.connectors.google_auth import GoogleApiClient, GoogleApiError
from app.connectors.google_properties import list_google_properties
from app.core.crypto import decrypt_secret
from app.db import get_db
from app.models.connection import GoogleConnection
from app.models.report import SavedReport
from app.schemas.google import PropertyListResult, PropertySelection
from app.services.property_selection import validate_property_selection


router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("/google")
def google_status(
    db: Session = Depends(get_db),
    _: str = Depends(require_owner),
) -> dict[str, bool | str | None]:
    connection = db.scalar(select(GoogleConnection).where(GoogleConnection.id == 1))
    return {
        "connected": connection is not None,
        "reconnect_required": connection.reconnect_required if connection else False,
        "search_console_site": connection.search_console_site if connection else None,
        "ga4_property_id": connection.ga4_property_id if connection else None,
    }


@router.get("/google/properties", response_model=PropertyListResult)
def google_properties(
    db: Session = Depends(get_db),
    _: str = Depends(require_owner),
) -> PropertyListResult:
    try:
        return list_google_properties(GoogleApiClient(db))
    except GoogleApiError as exc:
        status_code = 401 if exc.code in {"not_connected", "reconnect_required"} else 502
        raise _api_error(exc, status_code) from exc


@router.put("/google/selection")
def select_google_properties(
    selection: PropertySelection,
    db: Session = Depends(get_db),
    _: str = Depends(require_owner),
) -> dict[str, str | None]:
    connection = db.get(GoogleConnection, 1)
    if connection is None:
        raise HTTPException(status_code=400, detail="Connect Google before selecting properties")
    if selection.search_console_site or selection.ga4_property_id:
        try:
            accessible = list_google_properties(GoogleApiClient(db))
        except GoogleApiError as exc:
            raise _api_error(exc, 401 if exc.code == "reconnect_required" else 502) from exc
        validate_property_selection(accessible, selection.search_console_site, selection.ga4_property_id)
    connection.search_console_site = selection.search_console_site
    connection.ga4_property_id = selection.ga4_property_id
    db.commit()
    return {
        "search_console_site": connection.search_console_site,
        "ga4_property_id": connection.ga4_property_id,
    }


def _api_error(exc: GoogleApiError, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail=exc.message)


@router.delete("/google", status_code=204)
def disconnect_google(
    db: Session = Depends(get_db),
    _: str = Depends(require_owner),
) -> Response:
    connection = db.scalar(select(GoogleConnection).where(GoogleConnection.id == 1))
    if connection is not None:
        try:
            credentials = json.loads(decrypt_secret(connection.encrypted_credentials))
            token = credentials.get("refresh_token")
            if token:
                httpx.post(
                    "https://oauth2.googleapis.com/revoke",
                    data={"token": token},
                    timeout=5.0,
                ).raise_for_status()
        except (ValueError, httpx.HTTPError):
            # Local credential deletion still proceeds if Google's revoke endpoint is unavailable.
            pass
        db.execute(delete(GoogleConnection).where(GoogleConnection.id == 1))
    db.execute(delete(SavedReport))
    db.commit()
    return Response(status_code=204)
