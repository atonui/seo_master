from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import http.client
import ipaddress
import socket
import ssl
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from defusedxml import ElementTree

from app.core.config import get_settings
from app.schemas.audit import CrawlResult, PageAudit


USER_AGENT = "SparestrackerMarketingAgent/1.0"
MAX_PAGES = 100
MAX_REQUESTS = 500
MAX_RESPONSE_BYTES = 1_048_576
MAX_CRAWL_SECONDS = 120.0
MAX_SITEMAPS = 10
MAX_REDIRECTS = 5
MAX_REDIRECT_PORTS = {80, 443}
REDIRECT_CODES = {301, 302, 303, 307, 308}


class UnsafeUrlError(ValueError):
    pass


class ResponseTooLarge(ValueError):
    pass


@dataclass
class FetchResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def header(self, name: str) -> str:
        name = name.casefold()
        return next((value for key, value in self.headers.items() if key.casefold() == name), "")


@dataclass
class _FetchOutcome:
    response: FetchResponse | None
    final_url: str
    issue_codes: list[str]
    error: str | None = None


class _HtmlAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self.canonical: str | None = None
        self.robots: list[str] = []
        self.h1_count = 0
        self.links: list[tuple[str, bool]] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "title":
            self._in_title = True
        elif tag.casefold() == "meta":
            name = attributes.get("name", "").casefold()
            if name == "description" and self.description is None:
                self.description = attributes.get("content", "").strip() or None
            elif name in {"robots", "googlebot"}:
                self.robots.append(attributes.get("content", ""))
        elif tag.casefold() == "link":
            rel = {item.casefold() for item in attributes.get("rel", "").split()}
            if "canonical" in rel and self.canonical is None:
                self.canonical = attributes.get("href", "").strip() or None
        elif tag.casefold() == "h1":
            self.h1_count += 1
        elif tag.casefold() == "a":
            href = attributes.get("href", "").strip()
            if href:
                rel = {item.casefold() for item in attributes.get("rel", "").split()}
                self.links.append((href, "nofollow" in rel))

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False
            title = " ".join("".join(self._title_parts).split())
            if title:
                self.title = title[:500]
            self._title_parts.clear()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


def _canonical_host(host: str) -> str:
    try:
        return host.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise UnsafeUrlError("invalid internationalized hostname") from exc


def _resolve_host(host: str) -> list[str]:
    try:
        return sorted({item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise UnsafeUrlError("hostname did not resolve") from exc


def validate_site_url(site_url: str) -> str:
    try:
        parsed = urlsplit(site_url.strip())
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("site URL is malformed") from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("site URL must use HTTP or HTTPS and include a hostname")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise UnsafeUrlError("site URL cannot contain credentials, query parameters, or fragments")
    if parsed.path not in {"", "/"}:
        raise UnsafeUrlError("site URL must be the domain origin without a path")
    host = _canonical_host(parsed.hostname)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeUrlError("IP-literal site URLs are not allowed")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrlError("local site hostnames are not allowed")
    expected_port = 443 if parsed.scheme.casefold() == "https" else 80
    if port is not None and port != expected_port:
        raise UnsafeUrlError("site URL must use the standard HTTP or HTTPS port")
    return urlunsplit((parsed.scheme.casefold(), host, "/", "", ""))


def _public_addresses(host: str, resolver: Callable[[str], list[str]]) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        raise UnsafeUrlError("IP-literal hosts are not allowed")
    if host.casefold() == "localhost" or host.casefold().endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrlError("local hostnames are not allowed")
    addresses = resolver(host)
    if not addresses:
        raise UnsafeUrlError("hostname did not resolve")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
            if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
                parsed = parsed.ipv4_mapped
            if not parsed.is_global:
                raise UnsafeUrlError("hostname resolves to a non-public address")
        except ValueError as exc:
            raise UnsafeUrlError("hostname returned an invalid address") from exc
    return addresses


def _normalize_safe_url(
    value: str,
    expected_host: str,
    resolver: Callable[[str], list[str]],
) -> tuple[str, list[str]]:
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("malformed URL") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise UnsafeUrlError("only HTTP and HTTPS URLs are allowed")
    if parsed.username is not None or parsed.password is not None or not parsed.hostname:
        raise UnsafeUrlError("URL credentials or missing hostname are not allowed")
    host = _canonical_host(parsed.hostname)
    if host != expected_host:
        raise UnsafeUrlError("URL leaves the configured site host")
    port = parsed_port or (443 if parsed.scheme.casefold() == "https" else 80)
    if port not in MAX_REDIRECT_PORTS or (parsed.scheme.casefold() == "https" and port != 443) or (parsed.scheme.casefold() == "http" and port != 80):
        raise UnsafeUrlError("non-standard ports are not allowed")
    addresses = _public_addresses(host, resolver)
    path = parsed.path or "/"
    normalized = urlunsplit((parsed.scheme.casefold(), host, path, "", ""))
    return normalized, addresses


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(_PinnedHTTPConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(host, address, port, timeout)
        self._context = ssl.create_default_context()

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _fetch_pinned(url: str, addresses: list[str], max_bytes: int, timeout: float) -> FetchResponse:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address = addresses[0]
    connection_type = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    connection = connection_type(host, address, port, timeout)
    path = parsed.path or "/"
    try:
        connection.request("GET", path, headers={
            "Host": host,
            "User-Agent": USER_AGENT,
            "Accept": "text/html, application/xhtml+xml, application/xml, text/plain;q=0.5",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        response = connection.getresponse()
        headers = {key: value for key, value in response.getheaders()}
        content_length = next((value for key, value in headers.items() if key.casefold() == "content-length"), "")
        if content_length.isdigit() and int(content_length) > max_bytes:
            raise ResponseTooLarge("response exceeded the configured size limit")
        body = bytearray()
        while len(body) <= max_bytes:
            chunk = response.read(min(16_384, max_bytes + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLarge("response exceeded the configured size limit")
        return FetchResponse(status_code=response.status, headers=headers, body=bytes(body))
    finally:
        connection.close()


def _page_url(value: str, base_url: str) -> str:
    try:
        parsed = urlsplit(urljoin(base_url, value.strip()))
        if parsed.username is not None or parsed.password is not None:
            return ""
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))
    except ValueError:
        return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


class SiteCrawler:
    def __init__(
        self,
        site_url: str,
        *,
        max_pages: int | None = None,
        max_requests: int | None = None,
        max_response_bytes: int | None = None,
        timeout_seconds: float | None = None,
        delay_seconds: float | None = None,
        max_duration_seconds: float | None = None,
        fetcher: Callable[[str], FetchResponse] | None = None,
        resolver: Callable[[str], list[str]] = _resolve_host,
    ):
        settings = get_settings()
        self.site_url = site_url
        max_pages = settings.crawler_max_pages if max_pages is None else max_pages
        max_requests = settings.crawler_max_requests if max_requests is None else max_requests
        max_response_bytes = settings.crawler_max_response_bytes if max_response_bytes is None else max_response_bytes
        timeout_seconds = settings.crawler_timeout_seconds if timeout_seconds is None else timeout_seconds
        delay_seconds = settings.crawler_delay_seconds if delay_seconds is None else delay_seconds
        max_duration_seconds = settings.crawler_max_duration_seconds if max_duration_seconds is None else max_duration_seconds
        self._requested_max_pages = max_pages
        self._requested_max_requests = max_requests
        self._requested_max_response_bytes = max_response_bytes
        self._requested_max_duration_seconds = max_duration_seconds
        self.max_pages = min(max_pages, MAX_PAGES)
        self.max_requests = min(max_requests, MAX_REQUESTS)
        self.max_response_bytes = min(max_response_bytes, MAX_RESPONSE_BYTES)
        self.timeout_seconds = timeout_seconds
        self.delay_seconds = delay_seconds
        self.max_duration_seconds = min(max_duration_seconds, MAX_CRAWL_SECONDS)
        self.fetcher = fetcher
        self.resolver = resolver
        self.request_count = 0
        self.complete = True
        self.warnings: list[str] = []
        self.robots = RobotFileParser()
        self.robots.set_url("")
        self._robots_loaded = False
        self._last_request_at = 0.0
        self._host = ""
        self._deadline = 0.0

    def _safe_normalize(self, url: str) -> tuple[str, list[str]]:
        return _normalize_safe_url(url, self._host, self.resolver)

    def _can_fetch(self, url: str) -> bool:
        return not self._robots_loaded or self.robots.can_fetch(USER_AGENT, url)

    def _request(self, value: str, *, for_robots: bool = False) -> _FetchOutcome:
        current = value
        issues: list[str] = []
        for redirect_count in range(MAX_REDIRECTS + 1):
            try:
                current, addresses = self._safe_normalize(current)
            except UnsafeUrlError as exc:
                return _FetchOutcome(None, value, ["unsafe_url"], str(exc))
            if not for_robots and not self._can_fetch(current):
                return _FetchOutcome(None, current, ["robots_disallowed"], "URL disallowed by robots.txt")
            if time.monotonic() >= self._deadline:
                self.complete = False
                return _FetchOutcome(None, current, ["time_limit"], "Crawler time limit reached")
            if self.request_count >= self.max_requests:
                self.complete = False
                return _FetchOutcome(None, current, ["request_limit"], "Crawler request limit reached")
            if self.delay_seconds > 0 and self.request_count:
                remaining = self.delay_seconds - (time.monotonic() - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self.request_count += 1
            self._last_request_at = time.monotonic()
            try:
                response = (
                    self.fetcher(current)
                    if self.fetcher is not None
                    else _fetch_pinned(current, addresses, self.max_response_bytes, self.timeout_seconds)
                )
            except ResponseTooLarge as exc:
                return _FetchOutcome(None, current, ["response_too_large"], str(exc))
            except (TimeoutError, socket.timeout) as exc:
                return _FetchOutcome(None, current, ["request_failed"], "Request timed out")
            except (OSError, http.client.HTTPException) as exc:
                return _FetchOutcome(None, current, ["request_failed"], "Network request failed")
            if len(response.body) > self.max_response_bytes:
                return _FetchOutcome(None, current, ["response_too_large"], "Response exceeded the configured size limit")
            if response.status_code not in REDIRECT_CODES:
                return _FetchOutcome(response, current, issues)
            location = response.header("Location")
            if not location:
                return _FetchOutcome(response, current, issues)
            next_url = _page_url(location, current)
            if redirect_count >= MAX_REDIRECTS:
                return _FetchOutcome(response, current, ["redirect_limit"], "Redirect limit reached")
            try:
                self._safe_normalize(next_url)
            except UnsafeUrlError as exc:
                return _FetchOutcome(response, current, ["redirect_blocked"], str(exc))
            current = next_url
        return _FetchOutcome(None, current, ["redirect_limit"], "Redirect limit reached")

    def _load_robots(self, origin: str) -> list[str]:
        self.robots = RobotFileParser()
        self.robots.set_url(urljoin(origin, "/robots.txt"))
        outcome = self._request(urljoin(origin, "/robots.txt"), for_robots=True)
        sitemap_urls: list[str] = []
        if outcome.response is None:
            self.complete = False
            self.warnings.append(f"Could not safely read robots.txt: {outcome.error or 'request failed'}")
            self.robots.parse(["User-agent: *", "Disallow: /"])
        elif outcome.response.status_code == 404:
            self.robots.parse([])
        elif outcome.response.status_code == 200:
            text = outcome.response.body.decode("utf-8", errors="replace").splitlines()
            self.robots.parse(text)
            sitemap_urls = self.robots.site_maps() or []
            crawl_delay = self.robots.crawl_delay(USER_AGENT)
            if crawl_delay is not None:
                self.delay_seconds = max(self.delay_seconds, float(crawl_delay))
        else:
            self.complete = False
            self.warnings.append(f"robots.txt returned HTTP {outcome.response.status_code}; crawling is disabled")
            self.robots.parse(["User-agent: *", "Disallow: /"])
        self._robots_loaded = True
        return sitemap_urls

    def _sitemap_pages(self, origin: str, sitemap_urls: list[str]) -> list[str]:
        queue = deque(sitemap_urls or [urljoin(origin, "/sitemap.xml")])
        visited: set[str] = set()
        pages: list[str] = []
        stopped_for_global_limit = False
        while queue and len(visited) < MAX_SITEMAPS:
            sitemap_url = _page_url(queue.popleft(), origin)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            outcome = self._request(sitemap_url)
            if outcome.response is None:
                if "request_limit" in outcome.issue_codes or "time_limit" in outcome.issue_codes:
                    self.complete = False
                    self.warnings.append(outcome.error or "Crawler stopped at a configured limit")
                    stopped_for_global_limit = True
                    break
                if "robots_disallowed" not in outcome.issue_codes:
                    self.complete = False
                    self.warnings.append(f"Could not read sitemap {sitemap_url}: {outcome.error or 'request failed'}")
                continue
            if outcome.response.status_code == 404:
                continue
            if outcome.response.status_code != 200:
                self.complete = False
                self.warnings.append(f"Sitemap returned HTTP {outcome.response.status_code}")
                continue
            try:
                root = ElementTree.fromstring(outcome.response.body)
                locations = [item.text.strip() for item in root.iter() if _local_name(item.tag) == "loc" and item.text and item.text.strip()]
            except Exception:
                self.complete = False
                self.warnings.append(f"Sitemap XML could not be parsed: {sitemap_url}")
                continue
            if _local_name(root.tag) == "sitemapindex":
                queue.extend(locations[:MAX_SITEMAPS])
            else:
                for location in locations:
                    try:
                        normalized, _ = self._safe_normalize(_page_url(location, origin))
                    except UnsafeUrlError:
                        self.warnings.append("Sitemap contained a URL outside the configured public site; it was skipped")
                        continue
                    if self._can_fetch(normalized):
                        pages.append(normalized)
                    else:
                        self.complete = False
                        self.warnings.append(f"Sitemap URL disallowed by robots.txt: {normalized}")
        if queue and not stopped_for_global_limit and len(visited) >= MAX_SITEMAPS:
            self.complete = False
            self.warnings.append("Sitemap discovery reached the configured sitemap limit")
        return pages

    def _audit_page(self, url: str, outcome: _FetchOutcome) -> tuple[PageAudit, list[str], list[str], bool]:
        response = outcome.response
        issues = list(outcome.issue_codes)
        if response is None:
            return PageAudit(url=url, status_code=None, indexable=False, issue_codes=issues or ["request_failed"]), [], [], False
        status = response.status_code
        if status >= 400:
            issues.append("http_error")
        if outcome.final_url != url:
            issues.append("redirected")
        if outcome.issue_codes:
            issues.extend(outcome.issue_codes)
        content_type = response.header("Content-Type").casefold()
        parser = _HtmlAuditParser()
        if status < 400 and ("text/html" in content_type or "application/xhtml+xml" in content_type):
            parser.feed(response.body.decode("utf-8", errors="replace"))
            parser.close()
        elif status < 400:
            issues.append("non_html")
        robots_values = list(parser.robots)
        x_robots = response.header("X-Robots-Tag")
        if x_robots:
            robots_values.append(x_robots)
        robots = ",".join(value.strip() for value in robots_values if value.strip()) or "index,follow"
        indexable = status < 400 and not any("noindex" in value.casefold() or re_token(value, "none") for value in robots_values)
        if status >= 400:
            issues.append("non_indexable_status")
        if not indexable:
            issues.append("noindex")
        if not parser.title:
            issues.append("missing_title")
        if not parser.description:
            issues.append("missing_description")
        canonical = _page_url(parser.canonical, url) if parser.canonical else None
        if not canonical:
            issues.append("missing_canonical")
        else:
            try:
                self._safe_normalize(canonical)
            except UnsafeUrlError:
                issues.append("cross_host_canonical")
        if parser.h1_count == 0:
            issues.append("missing_h1")
        elif parser.h1_count > 1:
            issues.append("multiple_h1")
        internal: list[str] = []
        followable_internal: list[str] = []
        external = 0
        follow_allowed = not any("nofollow" in value.casefold() or re_token(value, "none") for value in robots_values)
        for href, link_nofollow in parser.links:
            absolute = _page_url(href, url)
            parsed = urlsplit(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            try:
                host = _canonical_host(parsed.hostname or "")
            except UnsafeUrlError:
                external += 1
                continue
            if host == self._host:
                internal.append(absolute)
                if not link_nofollow:
                    followable_internal.append(absolute)
            else:
                external += 1
        links_to_follow = sorted(set(followable_internal)) if follow_allowed else []
        if not follow_allowed:
            links_to_follow = []
        page = PageAudit(
            url=url,
            status_code=status,
            title=parser.title,
            description=parser.description,
            canonical=canonical,
            robots=robots,
            indexable=indexable,
            h1_count=parser.h1_count,
            internal_link_count=len(internal),
            external_link_count=external,
            issue_codes=list(dict.fromkeys(issues)),
        )
        return page, internal, links_to_follow, status < 500 and status not in {401, 403, 429}

    def crawl(self) -> CrawlResult:
        now = datetime.now(timezone.utc)
        if self.max_pages < 1 or self.max_requests < 1 or self.max_response_bytes < 1 or self.timeout_seconds <= 0 or self.max_duration_seconds <= 0 or self.delay_seconds < 0:
            return CrawlResult(complete=False, retrieved_at=now, warnings=["Crawler limits must be positive"])
        if self.max_pages < 100:
            page_limit = self.max_pages
        else:
            page_limit = MAX_PAGES
        try:
            parsed = urlsplit(self.site_url)
            self._host = _canonical_host(parsed.hostname or "")
            origin, _ = self._safe_normalize(self.site_url)
        except ValueError as exc:
            return CrawlResult(complete=False, retrieved_at=now, warnings=[f"Blocked unsafe site URL: {exc}"])
        self._deadline = time.monotonic() + self.max_duration_seconds
        if self._requested_max_pages > MAX_PAGES:
            self.complete = False
            self.warnings.append(f"Page limit capped at {MAX_PAGES}")
        if self._requested_max_requests > MAX_REQUESTS:
            self.complete = False
            self.warnings.append(f"Request limit capped at {MAX_REQUESTS}")
        if self._requested_max_response_bytes > MAX_RESPONSE_BYTES:
            self.complete = False
            self.warnings.append(f"Response size limit capped at {MAX_RESPONSE_BYTES} bytes")
        if self._requested_max_duration_seconds > MAX_CRAWL_SECONDS:
            self.complete = False
            self.warnings.append(f"Crawl duration capped at {MAX_CRAWL_SECONDS:g} seconds")
        base = urlunsplit((urlsplit(origin).scheme, self._host, "/", "", ""))
        robots_sitemaps = self._load_robots(base)
        sitemap_pages = self._sitemap_pages(base, robots_sitemaps)
        queue = deque([base, *sitemap_pages])
        queued = set(queue)
        audits: list[PageAudit] = []
        outgoing: dict[str, list[str]] = {}
        visited: set[str] = set()
        stopped_for_global_limit = False
        while queue and len(audits) < page_limit:
            requested_url = queue.popleft()
            if requested_url in visited:
                continue
            visited.add(requested_url)
            outcome = self._request(requested_url)
            if "request_limit" in outcome.issue_codes or "time_limit" in outcome.issue_codes:
                self.complete = False
                self.warnings.append(outcome.error or "Crawler stopped at a configured limit")
                stopped_for_global_limit = True
                break
            if "robots_disallowed" in outcome.issue_codes:
                self.complete = False
                self.warnings.append(f"URL disallowed by robots.txt: {requested_url}")
                continue
            page, internal_links, links_to_follow, page_complete = self._audit_page(requested_url, outcome)
            audits.append(page)
            outgoing[requested_url] = internal_links
            self.complete = self.complete and page_complete
            if outcome.error:
                self.warnings.append(f"{requested_url}: {outcome.error}")
            for link in links_to_follow:
                if link not in queued and link not in visited:
                    queue.append(link)
                    queued.add(link)
        if queue and not stopped_for_global_limit and len(audits) >= page_limit:
            self.complete = False
            self.warnings.append("Page limit reached; some discovered pages were not audited")
        page_status = {page.url: page.status_code for page in audits}
        for page in audits:
            broken = sorted({link for link in outgoing.get(page.url, []) if page_status.get(link) is not None and page_status[link] >= 400})
            page.broken_links = broken
            if broken:
                page.issue_codes = list(dict.fromkeys([*page.issue_codes, "broken_internal_link"]))
        return CrawlResult(
            pages=audits,
            warnings=list(dict.fromkeys(self.warnings)),
            complete=self.complete,
            retrieved_at=now,
            request_count=self.request_count,
        )


def re_token(value: str, token: str) -> bool:
    return token in {part.strip().casefold() for part in value.replace(";", ",").split(",")}


def crawl_site(
    site_url: str,
    max_pages: int | None = None,
    *,
    max_requests: int | None = None,
    max_response_bytes: int | None = None,
    timeout_seconds: float | None = None,
    delay_seconds: float | None = None,
    max_duration_seconds: float | None = None,
    fetcher: Callable[[str], FetchResponse] | None = None,
    resolver: Callable[[str], list[str]] = _resolve_host,
) -> CrawlResult:
    crawler = SiteCrawler(
        site_url,
        max_pages=max_pages,
        max_requests=max_requests,
        max_response_bytes=max_response_bytes,
        timeout_seconds=timeout_seconds,
        delay_seconds=delay_seconds,
        max_duration_seconds=max_duration_seconds,
        fetcher=fetcher,
        resolver=resolver,
    )
    return crawler.crawl()
