from datetime import date, datetime, timezone
from typing import Any, Protocol

from app.connectors.google_auth import GoogleApiError
from app.schemas.google import ConnectorResult, GA4Row


GA4_ROW_LIMIT = 100_000
MAX_GA4_ROWS = 200_000
MAX_REPORT_DAYS = 400


class Requester(Protocol):
    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


def _parse_date(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _as_int(value: object) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _run_report(
    api: Requester,
    property_id: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    metrics: list[str],
    event_names: list[str] | None = None,
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    complete = True
    known_total: int | None = None
    for offset in range(0, MAX_GA4_ROWS, GA4_ROW_LIMIT):
        body: dict[str, Any] = {
            "dateRanges": [{"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}],
            "dimensions": [{"name": item} for item in dimensions],
            "metrics": [{"name": item} for item in metrics],
            "limit": str(GA4_ROW_LIMIT),
            "offset": str(offset),
        }
        if event_names:
            body["dimensionFilter"] = {"filter": {
                "fieldName": "eventName",
                "inListFilter": {"values": event_names, "caseSensitive": True},
            }}
        try:
            response = api.request_json("POST", url, body=body)
        except GoogleApiError as exc:
            warnings.append(exc.message)
            complete = False
            break
        raw_rows = response.get("rows", [])
        if not isinstance(raw_rows, list):
            raw_rows = []
            warnings.append("GA4 returned an unexpected row set")
            complete = False
        rows.extend(item for item in raw_rows if isinstance(item, dict))
        row_count = response.get("rowCount")
        if row_count is not None:
            try:
                known_total = int(row_count)
            except (TypeError, ValueError):
                pass
        if len(raw_rows) < GA4_ROW_LIMIT:
            break
    else:
        complete = False
        warnings.append("GA4 result reached the configured row limit; more rows may exist")
    if known_total is not None and known_total > len(rows):
        complete = False
        warnings.append("GA4 report was truncated at the configured row limit")
    return rows, complete, warnings


def query_ga4(
    api: Requester,
    property_id: str,
    start_date: date,
    end_date: date,
    event_names: list[str],
) -> ConnectorResult[list[GA4Row]]:
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if (end_date - start_date).days > MAX_REPORT_DAYS:
        raise ValueError(f"date range cannot exceed {MAX_REPORT_DAYS} days")
    if not property_id.isdigit():
        raise ValueError("property_id must contain only digits")

    traffic_rows, traffic_complete, warnings = _run_report(
        api, property_id, start_date, end_date,
        ["date", "landingPage", "sessionSourceMedium"],
        ["sessions", "engagementRate"],
    )
    event_rows, events_complete, event_warnings = _run_report(
        api, property_id, start_date, end_date,
        ["date", "eventName"], ["eventCount"], event_names or None,
    )
    warnings.extend(event_warnings)
    rows: list[GA4Row] = []
    for item in traffic_rows:
        try:
            dimensions = [str(value["value"]) for value in item["dimensionValues"]]
            metrics = [value["value"] for value in item["metricValues"]]
            rows.append(GA4Row(
                date=_parse_date(dimensions[0]),
                landing_page=dimensions[1],
                session_source_medium=dimensions[2],
                sessions=_as_int(metrics[0]),
                engagement_rate=_as_float(metrics[1]),
            ))
        except (KeyError, IndexError, TypeError, ValueError):
            traffic_complete = False
            warnings.append("Some GA4 traffic rows could not be normalized")
    for item in event_rows:
        try:
            dimensions = [str(value["value"]) for value in item["dimensionValues"]]
            metrics = [value["value"] for value in item["metricValues"]]
            rows.append(GA4Row(
                date=_parse_date(dimensions[0]),
                event_name=dimensions[1],
                event_count=_as_int(metrics[0]),
            ))
        except (KeyError, IndexError, TypeError, ValueError):
            events_complete = False
            warnings.append("Some GA4 event rows could not be normalized")

    complete = traffic_complete and events_complete
    return ConnectorResult(
        data=rows,
        retrieved_at=datetime.now(timezone.utc),
        complete=complete,
        warning="; ".join(dict.fromkeys(warnings)) or None,
        error_code="partial" if not complete else None,
    )
