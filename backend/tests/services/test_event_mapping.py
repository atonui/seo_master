from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models.connection import GoogleConnection
from app.schemas.google import GA4Row
from app.schemas.metrics import ReportingSettings
from app.services.event_mapping import map_funnel_events, save_event_mapping


def test_unmapped_invite_event_is_setup_needed() -> None:
    rows = [GA4Row(date=date(2026, 10, 1), event_name="invite_request_submitted", event_count=2)]

    result = map_funnel_events(rows, ReportingSettings(invite_submit_event=None))

    assert result.status == "setup_needed"
    assert result.invite_submissions is None


def test_event_mapping_uses_configured_names() -> None:
    rows = [
        GA4Row(date=date(2026, 10, 1), event_name="cta_click", event_count=4),
        GA4Row(date=date(2026, 10, 1), event_name="invite_submit", event_count=2),
        GA4Row(date=date(2026, 10, 1), event_name="unrelated_event", event_count=99),
    ]

    result = map_funnel_events(rows, ReportingSettings(cta_event="cta_click", invite_submit_event="invite_submit"))

    assert result.status == "ready"
    assert result.cta_clicks == 4
    assert result.invite_submissions == 2


def test_event_mapping_persists_only_configured_event_names() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(GoogleConnection(id=1, owner_email="owner@example.com", encrypted_credentials="encrypted"))
        db.commit()

        settings = save_event_mapping(db, "cta_click", "invite_submit")

        assert settings.cta_event == "cta_click"
        assert settings.invite_submit_event == "invite_submit"
        connection = db.get(GoogleConnection, 1)
        assert connection.encrypted_credentials == "encrypted"
    engine.dispose()
