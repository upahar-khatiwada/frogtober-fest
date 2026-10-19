"""Kankai scraper against saved HTML fixtures and a mock transport. Never touches the network.

Fixtures (tests/fixtures/scraper/): kankai_listing.html and kankai_notice_scanned_pdf.html are
trimmed copies of the real pages (fetched 2026-10-19); kankai_notice_body_text.html is
constructed in the same markup with a synthetic notice; kankai_robots.txt is the real file, abridged.
"""

from pathlib import Path

import httpx
import pytest

from ingest.scraper import (
    KANKAI_BASE_URL,
    KANKAI_LISTING_PATH,
    PoliteFetcher,
    is_procurement_title,
    parse_listing,
    parse_notice,
    scrape_kankai,
)
from tests.test_parse_docs import make_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "scraper"
UA = "TenderlyBot/0.1 (test)"
LISTING_URL = KANKAI_BASE_URL + KANKAI_LISTING_PATH
SCANNED_URL = KANKAI_BASE_URL + "/ne/content/invaitation-bids-0"
BODY_URL = KANKAI_BASE_URL + "/ne/content/invaitation-bids"
SCANNED_PDF_URL = KANKAI_BASE_URL + "/sites/kankaimun.gov.np/files/Suchana%20Dosro.pdf"
ANNEX_PDF_URL = KANKAI_BASE_URL + "/sites/kankaimun.gov.np/files/demo-annex.pdf"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class MockKankai:
    """The site as the fixtures describe it. Unknown URLs are 404s. Records every request."""

    def __init__(self, robots: bytes | None = None, robots_status: int = 200, overrides: dict | None = None):
        html = {"content-type": "text/html; charset=utf-8"}
        pdf = {"content-type": "application/pdf"}
        self.routes: dict[str, tuple[int, bytes, dict]] = {
            f"{KANKAI_BASE_URL}/robots.txt": (robots_status, robots if robots is not None else fixture("kankai_robots.txt"),
                                              {"content-type": "text/plain"}),
            LISTING_URL: (200, fixture("kankai_listing.html"), html),
            SCANNED_URL: (200, fixture("kankai_notice_scanned_pdf.html"), html),
            BODY_URL: (200, fixture("kankai_notice_body_text.html"), html),
            SCANNED_PDF_URL: (200, make_pdf([None]), pdf),
            ANNEX_PDF_URL: (200, make_pdf(["Annex 1: Bill of quantities - gravel 450 m3"]), pdf),
        }
        self.routes.update(overrides or {})
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body, headers = self.routes.get(str(request.url), (404, b"not found", {}))
        return httpx.Response(status, content=body, headers=headers)

    @property
    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_fetcher(site: MockKankai, cache_dir: Path, clock: FakeClock, min_delay_s: float = 10.0) -> PoliteFetcher:
    return PoliteFetcher(KANKAI_BASE_URL, user_agent=UA, cache_dir=cache_dir, min_delay_s=min_delay_s,
                         transport=httpx.MockTransport(site.handler), sleep=clock.sleep, clock=clock)


# --- parsing --------------------------------------------------------------------------


def test_parse_listing_real_markup():
    items, next_url = parse_listing(fixture("kankai_listing.html"), LISTING_URL)
    assert len(items) == 10
    assert all(i.url.startswith(KANKAI_BASE_URL + "/ne/content/") for i in items)
    assert next_url == LISTING_URL + "?page=1"
    procurement = [i for i in items if is_procurement_title(i.title)]
    assert [i.url for i in procurement][:2] == [SCANNED_URL, BODY_URL]
    assert len(procurement) == 4  # bids x2 + two medicine purchase notices; exam/meeting notices dropped


@pytest.mark.parametrize("title, keep", [
    ("Invaitation For Bids", True),  # real typo on the board
    ("सिलबन्दी दरभाउपत्र आह्वानको सूचना", True),
    ("आशयपत्र आह्वान", True),
    ("CBRF पदको परिक्षा तथा अन्तरवार्ता सम्बन्धी सूचना", False),
    ("सार्वजनिक विदाको दिन विद्यालय संचालन नगर्ने सम्बन्धी सूचना", False),
])
def test_procurement_title_filter(title, keep):
    assert is_procurement_title(title) is keep


def test_parse_notice_with_scanned_pdf_only():
    page = parse_notice(fixture("kankai_notice_scanned_pdf.html"), SCANNED_URL)
    assert page.title == "Invaitation For Bids"
    assert page.published == "2026-10-12T16:05:52+05:45"
    assert page.body_text == ""
    assert [(a.url, a.mime, a.length) for a in page.attachments] == [(SCANNED_PDF_URL, "application/pdf", 1274639)]


def test_parse_notice_body_text_drops_scripts():
    page = parse_notice(fixture("kankai_notice_body_text.html"), BODY_URL)
    assert page.title == "सिलबन्दी दरभाउपत्र आह्वानको सूचना"
    assert "लागत अनुमान: रु. ९,५०,०००/-" in page.body_text
    assert "२०८३।०७।२५" in page.body_text
    assert "tracker" not in page.body_text
    assert page.attachments[0].url == ANNEX_PDF_URL


# --- the run: politeness, caching, raw text ------------------------------------------------


def test_scrape_end_to_end_is_polite(tmp_path, clock):
    site = MockKankai()
    fetcher = make_fetcher(site, tmp_path, clock)
    out = scrape_kankai(fetcher, max_pages=1, max_notices=3)

    assert out.blocked is None
    assert site.urls[0] == f"{KANKAI_BASE_URL}/robots.txt"
    assert all(r.method == "GET" for r in site.requests)
    assert all(r.headers["user-agent"] == UA for r in site.requests)
    assert all(r.url.host == "kankaimun.gov.np" for r in site.requests)
    assert all("cookie" not in r.headers and "authorization" not in r.headers for r in site.requests)
    assert len(clock.sleeps) == len(site.requests) - 1 and all(s >= 10 for s in clock.sleeps)

    [notice] = out.notices
    assert notice.source_url == BODY_URL
    assert notice.raw_text.startswith("सिलबन्दी दरभाउपत्र आह्वानको सूचना\nSource: " + BODY_URL)
    assert "लागत अनुमान: रु. ९,५०,०००/-" in notice.raw_text
    assert "[Attachment: demo-annex.pdf]" in notice.raw_text and "gravel 450 m3" in notice.raw_text
    skipped = dict(out.skipped)
    assert "OCR is out of scope" in skipped[SCANNED_URL]
    assert len(out.skipped) == 2 and any("HTTP 404" in reason for reason in skipped.values())


def test_cached_pages_are_not_refetched(tmp_path, clock):
    first = scrape_kankai(make_fetcher(MockKankai(), tmp_path, clock), max_notices=3)
    offline = MockKankai(overrides={url: (500, b"", {}) for url in MockKankai().routes})
    second = scrape_kankai(make_fetcher(offline, tmp_path, clock), max_notices=3)
    assert second.notices == first.notices
    # Only the 404 (never cached) is asked for again; everything else comes from disk.
    assert len(offline.requests) == 1
    assert list(tmp_path.glob("*.body"))  # raw pages are on disk


def test_robots_crawl_delay_above_floor_wins(tmp_path, clock):
    site = MockKankai(robots=b"User-agent: *\nCrawl-delay: 25\n")
    scrape_kankai(make_fetcher(site, tmp_path, clock, min_delay_s=10), max_notices=1)
    assert clock.sleeps and min(clock.sleeps[1:]) >= 25


def test_robots_disallow_stops_before_any_page(tmp_path, clock):
    site = MockKankai(robots=b"User-agent: *\nDisallow: /ne/\n")
    out = scrape_kankai(make_fetcher(site, tmp_path, clock))
    assert out.notices == [] and "robots.txt disallows" in out.blocked
    assert site.urls == [f"{KANKAI_BASE_URL}/robots.txt"]


@pytest.mark.parametrize("status", [403, 500])
def test_unreadable_robots_means_no_scraping(tmp_path, clock, status):
    site = MockKankai(robots_status=status)
    out = scrape_kankai(make_fetcher(site, tmp_path, clock))
    assert out.blocked and out.notices == []
    assert site.urls == [f"{KANKAI_BASE_URL}/robots.txt"]


def test_missing_robots_allows(tmp_path, clock):
    site = MockKankai(robots_status=404)
    out = scrape_kankai(make_fetcher(site, tmp_path, clock), max_notices=2)
    assert out.blocked is None and len(out.notices) == 1


def test_rate_limited_stops_without_retry(tmp_path, clock):
    site = MockKankai(overrides={BODY_URL: (429, b"slow down", {})})
    out = scrape_kankai(make_fetcher(site, tmp_path, clock), max_notices=3)
    assert "HTTP 429" in out.blocked
    assert site.urls.count(BODY_URL) == 1
    assert ANNEX_PDF_URL not in site.urls  # nothing after the refusal


def test_off_host_attachment_is_not_fetched(tmp_path, clock):
    body = fixture("kankai_notice_body_text.html").replace(ANNEX_PDF_URL.encode(), b"https://files.example.org/annex.pdf")
    site = MockKankai(overrides={BODY_URL: (200, body, {"content-type": "text/html"})})
    out = scrape_kankai(make_fetcher(site, tmp_path, clock), max_notices=2)
    assert all(r.url.host == "kankaimun.gov.np" for r in site.requests)
    assert len(out.notices) == 1 and "[Attachment" not in out.notices[0].raw_text
