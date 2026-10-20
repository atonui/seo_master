from datetime import date

from app.schemas.google import GA4Row, SearchRow
from app.schemas.metrics import ReportingSettings
from app.services.metric_normalization import normalize_metrics


def test_search_and_ga_metrics_are_normalized_daily_and_weighted() -> None:
    search_rows = [
        SearchRow(date=date(2026, 10, 1), clicks=10, impressions=100, ctr=0.1, position=5, is_aggregate=True),
        SearchRow(date=date(2026, 10, 1), clicks=1, impressions=20, ctr=0.05, position=8, query="bearing", page="/parts"),
    ]
    ga_rows = [
        GA4Row(date=date(2026, 10, 1), landing_page="/", session_source_medium="google / organic", sessions=20, engagement_rate=0.6),
        GA4Row(date=date(2026, 10, 1), event_name="cta_click", event_count=4),
        GA4Row(date=date(2026, 10, 1), event_name="invite_submit", event_count=2),
    ]

    points = normalize_metrics(
        search_rows,
        ga_rows,
        ReportingSettings(cta_event="cta_click", invite_submit_event="invite_submit"),
        date(2026, 10, 1),
        date(2026, 10, 2),
        search_complete=True,
        ga_complete=True,
    )
    values = {(point.date, point.metric): point for point in points}

    assert values[(date(2026, 10, 1), "clicks")].value == 10
    assert values[(date(2026, 10, 1), "ctr")].value == 0.1
    assert values[(date(2026, 10, 1), "average_position")].value == 5
    assert values[(date(2026, 10, 1), "engagement_rate")].weight == 20
    assert values[(date(2026, 10, 1), "cta_clicks")].value == 4
    assert values[(date(2026, 10, 1), "invite_submissions")].value == 2
    assert values[(date(2026, 10, 2), "clicks")].value == 0
    assert values[(date(2026, 10, 2), "sessions")].value == 0


def test_unmapped_invitation_event_is_not_normalized_as_zero_conversions() -> None:
    ga_rows = [GA4Row(date=date(2026, 10, 1), event_name="invite_submit", event_count=2)]

    points = normalize_metrics(
        [], ga_rows, ReportingSettings(), date(2026, 10, 1), date(2026, 10, 1),
        search_complete=True, ga_complete=True,
    )

    assert all(point.metric != "invite_submissions" for point in points)
    assert any(point.metric == "event_count:invite_submit" and point.value == 2 for point in points)
