from datetime import date
from typing import Any

from app.connectors.ga4 import query_ga4


class StubApi:
    def __init__(self, results: list[dict[str, Any]]):
        self.results = results
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((url, body))
        result = self.results.pop(0)
        if "__error__" in result:
            raise result["__error__"]
        return result


def test_ga4_rows_parse_landing_source_and_event_dimensions() -> None:
    api = StubApi([
        {"rowCount": 1, "rows": [{"dimensionValues": [{"value": "20261001"}, {"value": "/"}, {"value": "google / organic"}], "metricValues": [{"value": "20"}, {"value": "0.6"}]}]},
        {"rowCount": 1, "rows": [{"dimensionValues": [{"value": "20261001"}, {"value": "invite_request_submitted"}], "metricValues": [{"value": "2"}]}]},
    ])

    result = query_ga4(api, "123456789", date(2026, 10, 1), date(2026, 10, 7), ["invite_request_submitted"])

    assert result.complete is True
    assert len(result.data) == 2
    assert result.data[0].landing_page == "/"
    assert result.data[0].sessions == 20
    assert result.data[1].event_name == "invite_request_submitted"
    assert result.data[1].event_count == 2
    assert api.calls[0][1]["dimensions"][1]["name"] == "landingPage"


def test_ga4_empty_event_report_is_not_an_api_failure() -> None:
    result = query_ga4(StubApi([{"rowCount": 0}, {"rowCount": 0}]), "123456789", date(2026, 10, 1), date(2026, 10, 7), [])

    assert result.complete is True
    assert result.data == []


def test_ga4_quota_and_timeout_are_reported_as_partial_results() -> None:
    from app.connectors.google_auth import GoogleApiError

    api = StubApi([{"rowCount": 1, "rows": [{"dimensionValues": [{"value": "20261001"}, {"value": "/"}, {"value": "google / organic"}], "metricValues": [{"value": "10"}, {"value": "0.5"}]}]}, {"__error__": GoogleApiError("timeout", "GA4 request timed out")}])

    result = query_ga4(api, "123456789", date(2026, 10, 1), date(2026, 10, 7), [])

    assert result.complete is False
    assert len(result.data) == 1
    assert "timed out" in (result.warning or "")
