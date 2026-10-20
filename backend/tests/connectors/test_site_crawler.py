from collections.abc import Callable

import pytest

from app.connectors.site_crawler import FetchResponse, crawl_site, validate_site_url


BASE = "https://sparestracker.com"
ROBOTS = b"User-agent: *\nAllow: /\nSitemap: https://sparestracker.com/sitemap.xml\n"
PUBLIC_IPS = lambda host: ["93.184.216.34"]


def run_crawl(
    responses: dict[str, FetchResponse | Exception],
    max_pages: int = 100,
    **kwargs: object,
):
    requested: list[str] = []

    def fetch(url: str) -> FetchResponse:
        requested.append(url)
        result = responses[url]
        if isinstance(result, Exception):
            raise result
        return result

    result = crawl_site(BASE, max_pages=max_pages, fetcher=fetch, resolver=PUBLIC_IPS, delay_seconds=0, **kwargs)
    return result, requested


def response(status: int = 200, body: bytes = b"", **headers: str) -> FetchResponse:
    return FetchResponse(status_code=status, headers=headers, body=body)


def test_crawler_discovers_pages_from_sitemap() -> None:
    xml = b"<urlset><url><loc>https://sparestracker.com/</loc></url><url><loc>https://sparestracker.com/about</loc></url></urlset>"
    responses = {
        f"{BASE}/robots.txt": response(body=ROBOTS),
        f"{BASE}/sitemap.xml": response(body=xml, **{"Content-Type": "application/xml"}),
        f"{BASE}/": response(body=b"<html><title>Home</title><h1>Welcome</h1></html>", **{"Content-Type": "text/html"}),
        f"{BASE}/about": response(body=b"<html><title>About</title><h1>About</h1></html>", **{"Content-Type": "text/html"}),
    }

    result, _ = run_crawl(responses)

    assert {page.url for page in result.pages} == {f"{BASE}/", f"{BASE}/about"}
    assert result.complete is True


def test_page_limit_is_respected() -> None:
    xml = b"<urlset>" + b"".join(f"<url><loc>{BASE}/p{i}</loc></url>".encode() for i in range(5)) + b"</urlset>"
    responses = {
        f"{BASE}/robots.txt": response(body=ROBOTS),
        f"{BASE}/sitemap.xml": response(body=xml, **{"Content-Type": "application/xml"}),
        f"{BASE}/": response(body=b"<h1>Home</h1>", **{"Content-Type": "text/html"}),
        **{f"{BASE}/p{i}": response(body=b"<h1>Page</h1>", **{"Content-Type": "text/html"}) for i in range(5)},
    }

    result, _ = run_crawl(responses, max_pages=2)

    assert len(result.pages) == 2
    assert result.complete is False


def test_robots_disallow_is_obeyed() -> None:
    robots = b"User-agent: *\nDisallow: /private\nSitemap: https://sparestracker.com/sitemap.xml\n"
    xml = b"<urlset><url><loc>https://sparestracker.com/private</loc></url></urlset>"
    responses = {
        f"{BASE}/robots.txt": response(body=robots),
        f"{BASE}/sitemap.xml": response(body=xml, **{"Content-Type": "application/xml"}),
        f"{BASE}/": response(body=b"<h1>Home</h1>", **{"Content-Type": "text/html"}),
    }

    result, requested = run_crawl(responses)

    assert f"{BASE}/private" not in requested
    assert any("robots" in warning.lower() for warning in result.warnings)


def test_missing_metadata_and_h1_are_reported() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b"<html><head></head><body><p>No headings</p></body></html>", **{"Content-Type": "text/html"}),
    }

    result, _ = run_crawl(responses)
    page = result.pages[0]

    assert page.title is None
    assert page.description is None
    assert page.canonical is None
    assert page.h1_count == 0
    assert {"missing_title", "missing_description", "missing_canonical", "missing_h1"}.issubset(page.issue_codes)


def test_noindex_is_detected_from_page_and_response_robots_directives() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(
            body=b'<title>Home</title><meta name="description" content="Home"><meta name="robots" content="noindex,follow"><h1>Home</h1>',
            **{"Content-Type": "text/html", "X-Robots-Tag": "noindex"},
        ),
    }

    result, _ = run_crawl(responses)
    page = result.pages[0]

    assert page.indexable is False
    assert "noindex" in page.issue_codes
    assert "noindex" in page.robots


def test_broken_internal_links_are_attached_to_source_page() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b'<title>Home</title><meta name="description" content="Home"><link rel="canonical" href="https://sparestracker.com/"><h1>Home</h1><a href="/missing">broken</a>', **{"Content-Type": "text/html"}),
        f"{BASE}/missing": response(status=404),
    }

    result, _ = run_crawl(responses)
    home = next(page for page in result.pages if page.url == f"{BASE}/")

    assert home.broken_links == [f"{BASE}/missing"]
    assert "broken_internal_link" in home.issue_codes
    assert home.canonical == f"{BASE}/"


def test_nofollow_links_are_counted_but_not_crawled() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b'<h1>Home</h1><a rel="nofollow" href="/ignored">ignored</a>', **{"Content-Type": "text/html"}),
    }

    result, requested = run_crawl(responses)
    home = result.pages[0]

    assert home.internal_link_count == 1
    assert f"{BASE}/ignored" not in requested


def test_credentials_in_public_links_are_neither_fetched_nor_retained() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b'<h1>Home</h1><a href="https://owner:secret@sparestracker.com/private">link</a>', **{"Content-Type": "text/html"}),
    }

    result, requested = run_crawl(responses)

    assert all("secret" not in url for url in requested)
    assert "secret" not in result.model_dump_json()


def test_redirect_to_external_or_private_address_is_blocked() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b'<title>Home</title><meta name="description" content="Home"><h1>Home</h1><a href="/redirect">go</a>', **{"Content-Type": "text/html"}),
        f"{BASE}/redirect": response(status=302, Location="http://127.0.0.1/admin"),
    }

    result, requested = run_crawl(responses)
    redirect_page = next(page for page in result.pages if page.url == f"{BASE}/redirect")

    assert "redirect_blocked" in redirect_page.issue_codes
    assert all("127.0.0.1" not in url for url in requested)


def test_redirect_to_a_different_public_host_is_blocked() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b'<h1>Home</h1><a href="/redirect">go</a>', **{"Content-Type": "text/html"}),
        f"{BASE}/redirect": response(status=302, Location="https://attacker.example/path"),
    }

    result, requested = run_crawl(responses)
    redirect_page = next(page for page in result.pages if page.url == f"{BASE}/redirect")

    assert "redirect_blocked" in redirect_page.issue_codes
    assert all("attacker.example" not in url for url in requested)


def test_localhost_and_private_ip_start_urls_are_rejected_before_fetch() -> None:
    requests: list[str] = []

    def fetch(url: str) -> FetchResponse:
        requests.append(url)
        return response()

    for url in ("http://localhost", "http://192.168.1.1", "http://127.0.0.1"):
        result = crawl_site(url, fetcher=fetch, resolver=PUBLIC_IPS)
        assert result.pages == []
        assert result.complete is False
        assert any("unsafe" in warning.lower() for warning in result.warnings)
    assert requests == []


def test_site_url_setting_accepts_only_a_public_web_origin_shape() -> None:
    assert validate_site_url("https://Sparestracker.com/") == BASE + "/"
    for unsafe in (
        "http://127.0.0.1/",
        "http://localhost/",
        "https://sparestracker.com:8443/",
        "https://sparestracker.com/path",
        "https://sparestracker.com/?email=someone@example.com",
        "https://owner:secret@sparestracker.com/",
    ):
        with pytest.raises(ValueError):
            validate_site_url(unsafe)


def test_public_hostname_with_private_dns_answer_is_rejected() -> None:
    requests: list[str] = []
    result = crawl_site(
        BASE,
        fetcher=lambda url: (requests.append(url) or response()),
        resolver=lambda host: ["10.0.0.8"],
    )

    assert result.pages == []
    assert result.complete is False
    assert requests == []


@pytest.mark.parametrize("failure", [TimeoutError("timed out")])
def test_timeout_and_oversized_responses_are_reported(failure: Exception) -> None:
    timeout_responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": failure,
    }
    result, _ = run_crawl(timeout_responses)
    assert result.complete is False
    assert "request_failed" in result.pages[0].issue_codes

    oversized = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b"x" * (1024 * 1024 + 1), **{"Content-Type": "text/html"}),
    }
    result, _ = run_crawl(oversized, max_response_bytes=1024 * 1024)
    assert result.complete is False
    assert "response_too_large" in result.pages[0].issue_codes


def test_total_request_limit_stops_the_crawl() -> None:
    responses = {
        f"{BASE}/robots.txt": response(status=404),
        f"{BASE}/sitemap.xml": response(status=404),
        f"{BASE}/": response(body=b"<h1>Home</h1>", **{"Content-Type": "text/html"}),
    }

    result, requested = run_crawl(responses, max_requests=2)

    assert result.complete is False
    assert result.request_count == 2
    assert f"{BASE}/" not in requested
