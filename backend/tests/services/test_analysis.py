from datetime import date, datetime, timezone

from app.schemas.audit import CrawlResult
from app.schemas.google import GA4Row, SearchRow
from app.schemas.metrics import ReportingSettings
from app.services.analysis import analyze_report


DAY = date(2026, 10, 1)


def crawl():
    return CrawlResult(pages=[], complete=True, retrieved_at=datetime.now(timezone.utc))


def test_high_impressions_low_ctr_creates_click_opportunity():
    findings = analyze_report(
        [SearchRow(date=DAY, query="used tractor parts", clicks=8, impressions=1200, ctr=8 / 1200, position=4.0)],
        [], crawl(), ReportingSettings(),
    )
    assert len(findings) == 1
    assert findings[0].code == "search_low_ctr"
    assert findings[0].evidence[0].value == 1200


def test_low_search_sample_is_inconclusive():
    findings = analyze_report(
        [SearchRow(date=DAY, query="rare part", clicks=0, impressions=30, ctr=0.0, position=5.0)],
        [], crawl(), ReportingSettings(),
    )
    assert findings == []


def test_missing_invite_event_mapping_never_claims_zero_conversions():
    findings = analyze_report(
        [], [GA4Row(date=DAY, sessions=80)], crawl(), ReportingSettings(),
    )
    assert all("conversion" not in finding.summary.casefold() for finding in findings)


def test_aggregate_search_row_is_not_mistaken_for_a_query():
    row = SearchRow(date=DAY, clicks=0, impressions=300, ctr=0.0, position=2.0, is_aggregate=True)
    assert analyze_report([row], [], crawl(), ReportingSettings()) == []
