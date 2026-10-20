from fastapi import HTTPException

from app.schemas.google import PropertyListResult


def validate_property_selection(
    accessible: PropertyListResult,
    search_console_site: str | None,
    ga4_property_id: str | None,
) -> None:
    if search_console_site:
        if any("Search Console" in warning for warning in accessible.warnings):
            raise HTTPException(status_code=503, detail="Search Console properties could not be verified")
        if search_console_site not in {item.site_url for item in accessible.search_console}:
            raise HTTPException(status_code=400, detail="Selected Search Console site is not accessible to this Google account")
    if ga4_property_id:
        if any("GA4" in warning for warning in accessible.warnings):
            raise HTTPException(status_code=503, detail="GA4 properties could not be verified")
        if ga4_property_id not in {item.property_id for item in accessible.ga4}:
            raise HTTPException(status_code=400, detail="Selected GA4 property is not accessible to this Google account")
