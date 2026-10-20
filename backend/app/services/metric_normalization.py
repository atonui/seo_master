from collections import defaultdict
from datetime import date, timedelta

from app.schemas.google import GA4Row, SearchRow
from app.schemas.metrics import MetricPoint, ReportingSettings


MAX_NORMALIZED_DAYS = 400


def _date_range(start_date: date, end_date: date) -> list[date]:
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if (end_date - start_date).days > MAX_NORMALIZED_DAYS:
        raise ValueError(f"date range cannot exceed {MAX_NORMALIZED_DAYS} days")
    return [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]


def normalize_metrics(
    search_rows: list[SearchRow],
    ga_rows: list[GA4Row],
    settings: ReportingSettings,
    start_date: date,
    end_date: date,
    *,
    search_complete: bool,
    ga_complete: bool,
) -> list[MetricPoint]:
    days = _date_range(start_date, end_date)
    points: list[MetricPoint] = []

    search_daily: dict[date, dict[str, float]] = defaultdict(lambda: {
        "clicks": 0.0, "impressions": 0.0, "weighted_position": 0.0,
    })
    for row in search_rows:
        if not row.is_aggregate:
            continue
        bucket = search_daily[row.date]
        bucket["clicks"] += row.clicks
        bucket["impressions"] += row.impressions
        bucket["weighted_position"] += row.position * row.impressions
    search_days = days if search_complete else sorted(search_daily)
    for day in search_days:
        bucket = search_daily.get(day, {"clicks": 0.0, "impressions": 0.0, "weighted_position": 0.0})
        clicks = bucket["clicks"]
        impressions = bucket["impressions"]
        points.extend((
            MetricPoint(date=day, metric="clicks", value=clicks),
            MetricPoint(date=day, metric="impressions", value=impressions),
            MetricPoint(date=day, metric="ctr", value=(clicks / impressions if impressions else 0.0), weight=impressions),
            MetricPoint(date=day, metric="average_position", value=(bucket["weighted_position"] / impressions if impressions else 0.0), weight=impressions),
        ))

    ga_daily: dict[date, dict[str, float]] = defaultdict(lambda: {
        "sessions": 0.0, "engaged_sessions": 0.0, "event_count": 0.0,
    })
    landing_sessions: dict[tuple[date, str], float] = defaultdict(float)
    source_sessions: dict[tuple[date, str], float] = defaultdict(float)
    events: dict[tuple[date, str], float] = defaultdict(float)
    for row in ga_rows:
        if row.event_name is not None:
            events[(row.date, row.event_name)] += row.event_count
            continue
        bucket = ga_daily[row.date]
        bucket["sessions"] += row.sessions
        bucket["engaged_sessions"] += row.engagement_rate * row.sessions
        if row.landing_page is not None:
            landing_sessions[(row.date, row.landing_page)] += row.sessions
        if row.session_source_medium is not None:
            source_sessions[(row.date, row.session_source_medium)] += row.sessions
    ga_days = days if ga_complete else sorted({key[0] for key in events} | set(ga_daily))
    for day in ga_days:
        bucket = ga_daily.get(day, {"sessions": 0.0, "engaged_sessions": 0.0, "event_count": 0.0})
        sessions = bucket["sessions"]
        points.append(MetricPoint(date=day, metric="sessions", value=sessions))
        points.append(MetricPoint(
            date=day,
            metric="engagement_rate",
            value=(bucket["engaged_sessions"] / sessions if sessions else 0.0),
            weight=sessions,
        ))
        if settings.cta_event:
            points.append(MetricPoint(date=day, metric="cta_clicks", value=events.get((day, settings.cta_event), 0.0)))
        if settings.invite_submit_event:
            points.append(MetricPoint(date=day, metric="invite_submissions", value=events.get((day, settings.invite_submit_event), 0.0)))
    for (day, page), sessions in sorted(landing_sessions.items()):
        points.append(MetricPoint(date=day, metric=f"landing_sessions:{page}", value=sessions))
    for (day, source), sessions in sorted(source_sessions.items()):
        points.append(MetricPoint(date=day, metric=f"source_sessions:{source}", value=sessions))
    for (day, event), count in sorted(events.items()):
        points.append(MetricPoint(date=day, metric=f"event_count:{event}", value=count))
    return sorted(points, key=lambda point: (point.date, point.metric))
