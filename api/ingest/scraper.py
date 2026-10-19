"""Live tender scraper for ONE public source: Kankai Municipality's procurement notice board.

https://kankaimun.gov.np/ne/public-procurement-tender-notices is a standard MoFAGA Drupal
municipal site. Findings (2026-10-19, docs/NEPAL_CONTEXT.md section 6):
robots.txt allows the listing and /content/ notice pages and sets Crawl-delay: 10; no terms of
use page was found; no login is involved. bolpatra.gov.np, ppmo.gov.np and nea.org.np blocked or
reset our client, so they are not scraped (no UA spoofing, no evasion).

Rules this module enforces:
- robots.txt is fetched first and checked before every request; if it cannot be read
  (401/403/5xx/network error), nothing is fetched.
- At least `min_delay_s` (default 10 s, or the robots Crawl-delay if larger) between requests.
- An honest User-Agent. Only GETs, only on the source host, no cookies or logins.
- 401/403/429 stops the run at once (no retries, no workarounds).
- Every fetched page and attachment is cached raw on disk; cached pages are not refetched.
- Output is raw text only. Scout does all extraction.

Many notices are scanned image PDFs; without OCR (out of scope) they are skipped and reported.
The scraper is a bonus: the demo runs on the seed set (spec section 17).
"""

import hashlib
import json
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from ingest.notices import RawNotice
from ingest.parse_docs import ParseError, clean_text, parse_docx, parse_pdf

KANKAI_BASE_URL = "https://kankaimun.gov.np"
KANKAI_LISTING_PATH = "/ne/public-procurement-tender-notices"
LISTING_MAX_AGE_S = 6 * 3600  # the listing changes; notice pages and attachments are cached for good
MAX_BYTES = 10 * 1024 * 1024

# The board also carries exam, meeting and other notices. Titles are Nepali or English (typos included).
PROCUREMENT_KEYWORDS = (
    "bid", "tender", "quotation", "expression of interest", "eoi", "rfp", "proposal", "procurement",
    "बोलपत्र", "दरभाउपत्र", "सिलबन्दी", "आशयपत्र", "प्रस्ताव", "खरिद", "ठेक्का", "शुद्धिपत्र",
)


class ScrapeBlocked(RuntimeError):
    """The source said no (robots, 401/403/429) or robots.txt is unreachable. Stop the run."""


class FetchError(RuntimeError):
    """One URL failed (404, 5xx, too large, timeout). Skip it and carry on."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Fetched:
    url: str
    content: bytes
    content_type: str
    from_cache: bool


class PoliteFetcher:
    """GET-only, robots-checked, throttled, disk-cached HTTP client for one host."""

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        cache_dir: Path,
        min_delay_s: float = 10.0,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.host = urlsplit(self.base_url).netloc
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.min_delay_s = min_delay_s
        self._sleep, self._clock = sleep, clock
        self._last_request: float | None = None
        self._robots: RobotFileParser | None = None
        self.requests_made = 0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "ne,en;q=0.8"},
            timeout=timeout_s,
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    # --- robots ---------------------------------------------------------------

    def robots(self) -> RobotFileParser:
        if self._robots is None:
            url = f"{self.base_url}/robots.txt"
            try:
                fetched = self._get(url, max_age_s=24 * 3600, check_robots=False)
            except (FetchError, ScrapeBlocked) as exc:
                if isinstance(exc, FetchError) and exc.status == 404:  # no robots.txt: everything allowed
                    fetched = Fetched(url, b"", "text/plain", False)
                else:
                    raise ScrapeBlocked(f"robots.txt unavailable ({exc}); not fetching anything") from exc
            parser = RobotFileParser(url)
            parser.parse(fetched.content.decode("utf-8", errors="replace").splitlines())
            self._robots = parser
        return self._robots

    @property
    def delay_s(self) -> float:
        crawl_delay = self.robots().crawl_delay(self.user_agent)
        return max(self.min_delay_s, float(crawl_delay or 0))

    # --- fetching ---------------------------------------------------------------

    def get(self, url: str, *, max_age_s: float | None = None) -> Fetched:
        return self._get(url, max_age_s=max_age_s, check_robots=True)

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode()).hexdigest()[:40]
        return self.cache_dir / f"{key}.body", self.cache_dir / f"{key}.json"

    def _get(self, url: str, *, max_age_s: float | None, check_robots: bool) -> Fetched:
        if urlsplit(url).netloc != self.host or urlsplit(url).scheme not in ("http", "https"):
            raise FetchError(f"off-host URL not fetched: {url}")
        if check_robots and not self.robots().can_fetch(self.user_agent, url):
            raise ScrapeBlocked(f"robots.txt disallows {url}")
        body_path, meta_path = self._cache_paths(url)
        if body_path.is_file() and meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if max_age_s is None or time.time() - meta["fetched_at"] < max_age_s:
                return Fetched(url, body_path.read_bytes(), meta["content_type"], True)
        self._throttle(check_robots)
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise FetchError(f"{type(exc).__name__} for {url}") from exc
        finally:
            self._last_request = self._clock()
            self.requests_made += 1
        if response.status_code in (401, 403, 429):
            raise ScrapeBlocked(f"HTTP {response.status_code} for {url}; stopping (no retries)")
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code} for {url}", response.status_code)
        if len(response.content) > MAX_BYTES:
            raise FetchError(f"{url} is larger than {MAX_BYTES} bytes")
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(response.content)
        meta_path.write_text(json.dumps({"url": url, "content_type": content_type, "fetched_at": time.time()}),
                             encoding="utf-8")
        return Fetched(url, response.content, content_type, False)

    def _throttle(self, robots_known: bool) -> None:
        if self._last_request is None:
            return
        delay = self.delay_s if robots_known else self.min_delay_s
        wait = self._last_request + delay - self._clock()
        if wait > 0:
            self._sleep(wait)


# --- parsing (pure functions; tested against saved fixtures) ----------------------------


@dataclass(frozen=True)
class ListingItem:
    title: str
    url: str


@dataclass(frozen=True)
class Attachment:
    url: str
    name: str
    mime: str
    length: int | None


@dataclass
class NoticePage:
    url: str
    title: str
    published: str | None
    body_text: str
    attachments: list[Attachment] = field(default_factory=list)


def _soup(html: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _text(node) -> str:
    for junk in node.select("script, style, noscript"):
        junk.decompose()
    return clean_text(node.get_text("\n"))


def is_procurement_title(title: str) -> bool:
    t = unicodedata.normalize("NFC", title).casefold()
    return any(unicodedata.normalize("NFC", k) in t for k in PROCUREMENT_KEYWORDS)


def parse_listing(html: bytes | str, page_url: str) -> tuple[list[ListingItem], str | None]:
    """Notice links on one listing page, plus the next page's URL (None on the last page)."""
    soup = _soup(html)
    items = []
    for link in soup.select(".view-content .views-row .views-field-title a[href]"):
        title = clean_text(link.get_text(" "))
        if title:
            items.append(ListingItem(title, urljoin(page_url, link["href"])))
    nxt = soup.select_one(".pager-next a[href]")
    return items, (urljoin(page_url, nxt["href"]) if nxt else None)


def parse_notice(html: bytes | str, url: str) -> NoticePage:
    soup = _soup(html)
    node = soup.select_one(".node") or soup
    title_meta = node.select_one('[property="dc:title"][content]')
    heading = soup.select_one(".intro .section-title")
    if title_meta and title_meta["content"].strip():
        title = clean_text(title_meta["content"])
    elif heading:
        title = _text(heading)
    else:
        title = clean_text(soup.title.get_text().split("|")[0]) if soup.title else ""
    created = node.select_one('[property~="dc:created"][content]')
    body = node.select_one(".field-name-body .field-item")
    attachments = []
    for link in node.select(".field-name-field-supporting-documents a[href]"):
        mime, _, rest = (link.get("type") or "").partition(";")
        length = rest.strip().removeprefix("length=")
        attachments.append(Attachment(
            url=urljoin(url, link["href"]),
            name=clean_text(link.get_text(" ")),
            mime=mime.strip(),
            length=int(length) if length.isdigit() else None,
        ))
    return NoticePage(url, title, created["content"] if created else None, _text(body) if body else "", attachments)


def attachment_text(att: Attachment, fetched: Fetched) -> tuple[str, str | None]:
    """(text, reason it gave no text). Scanned PDFs and images need OCR, which is out of scope."""
    name = att.name.lower()
    kind = fetched.content_type or att.mime
    try:
        if kind == "application/pdf" or name.endswith(".pdf"):
            parsed = parse_pdf(fetched.content)
        elif name.endswith(".docx") or "wordprocessingml" in kind:
            parsed = parse_docx(fetched.content)
        else:
            return "", f"{att.name}: unsupported attachment type {kind or 'unknown'}"
    except ParseError as exc:
        return "", f"{att.name}: {exc}"
    if parsed.needs_ocr or not parsed.text.strip():
        return "", f"{att.name}: scanned image with no text layer (OCR is out of scope)"
    return parsed.text, None


# --- the run ---------------------------------------------------------------------


@dataclass
class ScrapeOutcome:
    notices: list[RawNotice] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    blocked: str | None = None


def _raw_text(page: NoticePage, parts: list[str]) -> str:
    header = [page.title, f"Source: {page.url}"]
    if page.published:
        header.append(f"Published on source: {page.published}")
    return "\n".join(header) + "\n\n" + "\n\n".join(parts)


def scrape_kankai(fetcher: PoliteFetcher, *, max_pages: int = 1, max_notices: int = 3) -> ScrapeOutcome:
    """Read the notice board, keep procurement notices, return their raw text.

    Stops early (outcome.blocked) the moment the site refuses us.
    """
    out = ScrapeOutcome()
    candidates: list[ListingItem] = []
    try:
        page_url: str | None = fetcher.base_url + KANKAI_LISTING_PATH
        for _ in range(max_pages):
            if page_url is None or len(candidates) >= max_notices:
                break
            listing = fetcher.get(page_url, max_age_s=LISTING_MAX_AGE_S)
            items, page_url = parse_listing(listing.content, listing.url)
            for item in items:
                if not is_procurement_title(item.title):
                    continue
                if item.url not in {c.url for c in candidates}:
                    candidates.append(item)
        for item in candidates[:max_notices]:
            try:
                fetched = fetcher.get(item.url)
            except FetchError as exc:
                out.skipped.append((item.url, str(exc)))
                continue
            page = parse_notice(fetched.content, item.url)
            parts = [page.body_text] if page.body_text else []
            reasons = []
            for att in page.attachments:
                if att.length is not None and att.length > MAX_BYTES:
                    reasons.append(f"{att.name}: larger than {MAX_BYTES} bytes")
                    continue
                try:
                    att_fetched = fetcher.get(att.url)
                except FetchError as exc:
                    reasons.append(f"{att.name}: {exc}")
                    continue
                text, reason = attachment_text(att, att_fetched)
                if text:
                    parts.append(f"[Attachment: {att.name}]\n{text}")
                if reason:
                    reasons.append(reason)
            if parts:
                out.notices.append(RawNotice(item.url, _raw_text(page, parts)))
            else:
                out.skipped.append((item.url, "; ".join(reasons) or "no body text and no attachments"))
    except ScrapeBlocked as exc:
        out.blocked = str(exc)
    return out
