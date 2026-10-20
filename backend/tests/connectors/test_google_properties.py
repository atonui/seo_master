from typing import Any

from app.connectors.google_properties import list_google_properties


class StubApi:
    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = responses

    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.responses.pop(0)
        if "__error__" in result:
            raise result["__error__"]
        return result


def test_accessible_properties_are_normalized() -> None:
    api = StubApi([
        {"siteEntry": [{"siteUrl": "sc-domain:sparestracker.com", "permissionLevel": "siteOwner"}]},
        {"accountSummaries": [{"displayName": "Sparestracker", "propertySummaries": [{"property": "properties/123456789", "displayName": "Sparestracker GA4"}]}]},
    ])

    result = list_google_properties(api)

    assert result.search_console[0].site_url == "sc-domain:sparestracker.com"
    assert result.ga4[0].property_id == "123456789"
    assert result.warnings == []


def test_no_accessible_properties_returns_empty_lists() -> None:
    result = list_google_properties(StubApi([{}, {}]))

    assert result.search_console == []
    assert result.ga4 == []


def test_one_property_source_can_fail_without_hiding_the_other() -> None:
    from app.connectors.google_auth import GoogleApiError

    result = list_google_properties(StubApi([
        {"__error__": GoogleApiError("permission", "Search Console permission denied")},
        {"accountSummaries": [{"displayName": "Account", "propertySummaries": [{"property": "properties/42", "displayName": "Analytics"}]}]},
    ]))

    assert result.search_console == []
    assert result.ga4[0].property_id == "42"
    assert result.warnings
