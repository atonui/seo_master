from collections import defaultdict
import hashlib

from app.schemas.audit import CrawlResult
from app.schemas.google import GA4Row, SearchRow
from app.schemas.metrics import ReportingSettings
from app.schemas.recommendation import Evidence, Finding


MIN_QUERY_IMPRESSIONS = 100
LOW_CTR = 0.02


def analyze_report(search_rows: list[SearchRow], ga_rows: list[GA4Row], crawl: CrawlResult, settings: ReportingSettings) -> list[Finding]:
    """Produce conservative, source-linked candidate findings from supplied report data."""
    del ga_rows, settings  # No conversion finding is emitted until its event is mapped.
    findings: list[Finding] = []
    query_rows: dict[str, list[SearchRow]] = defaultdict(list)
    for row in search_rows:
        if not row.is_aggregate and row.query:
            query_rows[row.query].append(row)
    for query, rows in sorted(query_rows.items()):
        impressions = sum(row.impressions for row in rows)
        clicks = sum(row.clicks for row in rows)
        if impressions < MIN_QUERY_IMPRESSIONS:
            continue
        ctr = clicks / impressions if impressions else 0.0
        avg_position = sum(row.position * row.impressions for row in rows) / impressions
        if ctr >= LOW_CTR or avg_position > 10:
            continue
        period = _period(row.date.isoformat() for row in rows)
        key = _safe_id(query)
        findings.append(Finding(
            code="search_low_ctr", title="Search result gets impressions but few clicks",
            summary=f'“{query}” received {impressions} impressions and {clicks} clicks ({ctr:.1%} CTR), at average position {avg_position:.1f}.',
            source="Google Search Console",
            evidence=[
                Evidence(id=f"gsc:{key}:impressions", metric="impressions", value=impressions, period=period, source="Google Search Console", label=query),
                Evidence(id=f"gsc:{key}:clicks", metric="clicks", value=clicks, period=period, source="Google Search Console", label=query),
                Evidence(id=f"gsc:{key}:ctr", metric="click-through rate", value=round(ctr, 6), period=period, source="Google Search Console", label=query),
                Evidence(id=f"gsc:{key}:position", metric="average position", value=round(avg_position, 2), period=period, source="Google Search Console", label=query),
            ], limitations=["CTR varies by query intent and search result features; this finding does not establish a cause."],
        ))

    checks = (
        ("missing_title", "technical_missing_title", "Page is missing a title"),
        ("missing_description", "technical_missing_description", "Page is missing a meta description"),
        ("missing_h1", "technical_missing_h1", "Page is missing an H1 heading"),
        ("not_indexable", "technical_not_indexable", "Page is marked non-indexable"),
    )
    for page in crawl.pages:
        issues = set(page.issue_codes)
        for issue_code, code, title in checks:
            if issue_code not in issues:
                continue
            findings.append(Finding(
                code=code, title=title, summary=f"{page.url} has a crawler-detected {title.casefold()} issue.",
                source="Sparestracker website crawl",
                evidence=[Evidence(id=f"crawl:{_safe_id(page.url)}:{issue_code}", metric=issue_code, value=True, period="crawl time", source="Sparestracker website crawl", label=page.url)],
                limitations=["A crawler can miss content rendered only by client-side JavaScript."],
            ))
        if page.broken_links:
            findings.append(Finding(
                code="technical_broken_links", title="Page links to URLs that returned errors",
                summary=f"{page.url} contains {len(page.broken_links)} link(s) that returned an error during the crawl.",
                source="Sparestracker website crawl",
                evidence=[Evidence(id=f"crawl:{_safe_id(page.url)}:broken_links", metric="broken link count", value=len(page.broken_links), period="crawl time", source="Sparestracker website crawl", label=page.url)],
                limitations=["The linked URL may have been temporarily unavailable during the crawl."],
            ))
    return findings


def _period(days) -> str:
    values = sorted(days)
    return values[0] if len(values) == 1 else f"{values[0]} to {values[-1]}"


def _safe_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
