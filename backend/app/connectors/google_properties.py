from typing import Protocol, Any

from app.connectors.google_auth import GoogleApiError
from app.schemas.google import GA4Property, PropertyListResult, SearchConsoleProperty


class Requester(Protocol):
    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


def list_google_properties(api: Requester) -> PropertyListResult:
    result = PropertyListResult()
    try:
        response = api.request_json("GET", "https://www.googleapis.com/webmasters/v3/sites")
        result.search_console = [
            SearchConsoleProperty(site_url=str(item["siteUrl"]), permission_level=str(item.get("permissionLevel", "unknown")))
            for item in response.get("siteEntry", [])
            if isinstance(item, dict) and item.get("siteUrl")
        ]
    except GoogleApiError as exc:
        if exc.code in {"not_connected", "reconnect_required"}:
            raise
        result.warnings.append(f"Search Console property list unavailable: {exc.message}")

    try:
        summaries: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(10):
            params: dict[str, Any] = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token
            response = api.request_json(
                "GET",
                "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                params=params,
            )
            summaries.extend(item for item in response.get("accountSummaries", []) if isinstance(item, dict))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        if page_token:
            result.warnings.append("GA4 property list reached the page limit; some properties may be missing")
        for account in summaries:
            account_name = str(account.get("displayName", "")) or None
            for prop in account.get("propertySummaries", []):
                if not isinstance(prop, dict):
                    continue
                resource_name = str(prop.get("property", ""))
                property_id = resource_name.removeprefix("properties/")
                if property_id.isdigit():
                    result.ga4.append(GA4Property(
                        property_id=property_id,
                        display_name=str(prop.get("displayName", property_id)),
                        account_name=account_name,
                    ))
    except GoogleApiError as exc:
        if exc.code in {"not_connected", "reconnect_required"}:
            raise
        result.warnings.append(f"GA4 property list unavailable: {exc.message}")

    result.search_console.sort(key=lambda item: item.site_url.casefold())
    result.ga4.sort(key=lambda item: (item.account_name or "", item.display_name.casefold(), item.property_id))
    return result
