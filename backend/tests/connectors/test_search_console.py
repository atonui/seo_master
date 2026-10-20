from datetime import date
from typing import Any

from app.connectors.search_console import query_search_performance


class StubApi:
    def __init__(self, results: list[dict[str, Any]]):
        self.results = results
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, url, body))
        result = self.results.pop(0)
        if "__error__" in result:
            raise result["__error__"]
        return result


def test_search_console_rows_are_normalized() -> None:
    api = StubApi([
        {"rows": [{"keys": ["2026-10-01"], "clicks": 5, "impressions": 60, "ctr": 0.0833, "position": 6.8}]},
        {"rows": [{"keys": ["2026-10-01", "bearing supplier", "https://sparestracker.com/"], "clicks": 4, "impressions": 50, "ctr": 0.08, "position": 7.4}]},
    ])

    result = query_search_performance(api, "sc-domain:sparestracker.com", date(2026, 10, 1), date(2026, 10, 7))

    assert result.complete is True
    aggregate, detail = result.data
    assert aggregate.is_aggregate is True
    assert aggregate.query is None
    assert aggregate.clicks == 5
    assert detail.query == "bearing supplier"
    assert detail.clicks == 4
    assert api.calls[0][2]["dimensions"] == ["date"]
    assert api.calls[1][2]["dimensions"] == ["date", "query", "page"]


def test_search_console_empty_result_is_complete() -> None:
    result = query_search_performance(StubApi([{}, {}]), "sc-domain:sparestracker.com", date(2026, 10, 1), date(2026, 10, 7))

    assert result.complete is True
    assert result.data == []


def test_search_console_partial_failure_is_marked_incomplete(monkeypatch) -> None:
    from app.connectors import search_console
    from app.connectors.google_auth import GoogleApiError

    monkeypatch.setattr(search_console, "SEARCH_ROW_LIMIT", 1)
    api = StubApi([
        {"rows": [{"keys": ["2026-10-01"], "clicks": 1, "impressions": 20, "ctr": 0.05, "position": 8}]},
        {"__error__": GoogleApiError("quota", "quota exceeded")},
        {},
    ])

    result = query_search_performance(api, "sc-domain:sparestracker.com", date(2026, 10, 1), date(2026, 10, 7))

    assert result.complete is False
    assert len(result.data) == 1
    assert "quota" in (result.warning or "").lower()
