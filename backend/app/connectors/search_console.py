from datetime import date, datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote

from app.connectors.google_auth import GoogleApiError
from app.schemas.google import ConnectorResult, SearchRow


SEARCH_ROW_LIMIT = 25_000
MAX_SEARCH_ROWS = 100_000
MAX_REPORT_DAYS = 400


class Requester(Protocol):
    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


def _number(value: object, default: int | float = 0) -> int | float:
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _query_rows(
    api: Requester,
    url: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    *,
    aggregate: bool,
) -> tuple[list[SearchRow], bool, list[str]]:
    rows: list[SearchRow] = []
    warnings: list[str] = []
    complete = True
    for start_row in range(0, MAX_SEARCH_ROWS, SEARCH_ROW_LIMIT):
        try:
            response = api.request_json("POST", url, body={
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": dimensions,
                "rowLimit": SEARCH_ROW_LIMIT,
                "startRow": start_row,
            })
        except GoogleApiError as exc:
            warnings.append(exc.message)
            complete = False
            break

        raw_rows = response.get("rows", [])
        if not isinstance(raw_rows, list):
            raw_rows = []
            warnings.append("Search Console returned an unexpected row set")
            complete = False
        for item in raw_rows:
            try:
                keys = item["keys"]
                rows.append(SearchRow(
                    date=date.fromisoformat(str(keys[0])),
                    query=None if aggregate else str(keys[1]),
                    page=None if aggregate else str(keys[2]),
                    clicks=int(_number(item.get("clicks"))),
                    impressions=int(_number(item.get("impressions"))),
                    ctr=float(_number(item.get("ctr"))),
                    position=float(_number(item.get("position"))),
                    is_aggregate=aggregate,
                ))
            except (KeyError, IndexError, TypeError, ValueError):
                complete = False
                warnings.append("Some Search Console rows could not be normalized")
        if len(raw_rows) < SEARCH_ROW_LIMIT:
            break
    else:
        complete = False
        warnings.append("Search Console result reached the configured row limit; more rows may exist")
    return rows, complete, warnings


def query_search_performance(
    api: Requester,
    site_url: str,
    start_date: date,
    end_date: date,
) -> ConnectorResult[list[SearchRow]]:
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if (end_date - start_date).days > MAX_REPORT_DAYS:
        raise ValueError(f"date range cannot exceed {MAX_REPORT_DAYS} days")

    url = f"https://www.googleapis.com/webmasters/v3/sites/{quote(site_url, safe='')}/searchAnalytics/query"
    daily_totals, totals_complete, totals_warnings = _query_rows(
        api, url, start_date, end_date, ["date"], aggregate=True,
    )
    detail_rows, details_complete, details_warnings = _query_rows(
        api, url, start_date, end_date, ["date", "query", "page"], aggregate=False,
    )
    rows = daily_totals + detail_rows
    complete = totals_complete and details_complete
    warnings = totals_warnings + details_warnings

    return ConnectorResult(
        data=rows,
        retrieved_at=datetime.now(timezone.utc),
        complete=complete,
        warning="; ".join(dict.fromkeys(warnings)) or None,
        error_code="partial" if not complete else None,
    )
