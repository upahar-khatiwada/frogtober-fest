"""POST /tenders/scrape: seed load, upsert by source_url, live source via a mocked site (needs Postgres)."""

import shutil

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from config import get_settings
from db.models import Match, Tender
from deps import get_kankai_fetcher, get_seed_dir, get_session, get_sessionmaker
from main import app
from tests.test_scraper import BODY_URL, KANKAI_BASE_URL, FakeClock, MockKankai, make_fetcher

SEED_DIR = get_settings().seed_tenders_dir


class NoNetwork:
    """Fails the test if anything tries to use the live scraper."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"seed load must not touch the network: {request.url}")


@pytest.fixture
def seed_dir(tmp_path):
    target = tmp_path / "seed_tenders"
    shutil.copytree(SEED_DIR, target)
    return target


@pytest.fixture
def make_api(session_factory, tmp_path):
    clients = []

    def _make(seed_dir, site=None) -> TestClient:
        def session():
            with session_factory() as s:
                yield s

        def fetcher():
            if site is None:
                from ingest.scraper import PoliteFetcher

                f = PoliteFetcher(KANKAI_BASE_URL, user_agent="t", cache_dir=tmp_path / "cache",
                                  transport=httpx.MockTransport(NoNetwork().handler))
            else:
                f = make_fetcher(site, tmp_path / "cache", FakeClock())
            yield f
            f.close()

        app.dependency_overrides.update({
            get_session: session, get_sessionmaker: lambda: session_factory,
            get_seed_dir: lambda: seed_dir, get_kankai_fetcher: fetcher,
        })
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    app.dependency_overrides.clear()


def test_seed_load_creates_new_raw_tenders_offline(make_api, seed_dir, db_session):
    api = make_api(seed_dir)
    response = api.post("/tenders/scrape")  # no body: seed is the default source
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["source"] == "seed"
    assert (report["created"], report["updated"], report["unchanged"]) == (37, 0, 0)
    assert report["blocked"] is None and report["skipped"] == []

    tenders = db_session.scalars(select(Tender).order_by(Tender.id)).all()
    assert [t.id for t in tenders] == report["tender_ids"]
    assert {t.status for t in tenders} == {"new"}
    first = tenders[0]
    assert first.source_url == "seed://seed_tenders/001_bhanu_road_gravelling.txt"
    assert first.raw_text.startswith("[SYNTHETIC SEED NOTICE")
    assert "Rs. 1,48,75,000/-" in first.raw_text
    # Raw text only: Scout fills everything else.
    assert all(t.title is None and t.record_json is None and t.estimated_cost_npr is None for t in tenders)


def test_reload_is_idempotent_and_keeps_progress(make_api, seed_dir, db_session):
    api = make_api(seed_dir)
    ids = api.post("/tenders/scrape", json={"source": "seed"}).json()["tender_ids"]
    tender = db_session.get(Tender, ids[0])
    tender.status, tender.title = "matched", "Bhanu-Satiswara road"
    db_session.commit()

    again = api.post("/tenders/scrape", json={"source": "seed"}).json()
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 37)
    assert again["tender_ids"] == ids
    db_session.refresh(tender)
    assert (tender.status, tender.title) == ("matched", "Bhanu-Satiswara road")


def test_changed_notice_is_reset_to_new(make_api, seed_dir, db_session):
    api = make_api(seed_dir)
    ids = api.post("/tenders/scrape").json()["tender_ids"]
    tender = db_session.get(Tender, ids[0])
    tender.status, tender.title, tender.record_json = "matched", "old title", {"title": "old"}
    db_session.add(Match(tender_id=tender.id, score=80, reasons=["fits"], decision="pursue"))
    db_session.commit()

    path = seed_dir / "001_bhanu_road_gravelling.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("2083-08-05", "2083-08-12"), encoding="utf-8")
    report = api.post("/tenders/scrape").json()
    assert (report["created"], report["updated"], report["unchanged"]) == (0, 1, 36)

    db_session.expire_all()
    tender = db_session.get(Tender, ids[0])
    assert tender.status == "new" and tender.title is None and tender.record_json is None
    assert "2083-08-12" in tender.raw_text
    assert db_session.scalars(select(Match).where(Match.tender_id == tender.id)).all() == []


def test_missing_seed_data_is_503(make_api, tmp_path):
    api = make_api(tmp_path / "nowhere")
    response = api.post("/tenders/scrape")
    assert response.status_code == 503 and "manifest" in response.json()["detail"]


def test_bad_request_is_422(make_api, seed_dir):
    api = make_api(seed_dir)
    assert api.post("/tenders/scrape", json={"source": "bolpatra"}).status_code == 422
    assert api.post("/tenders/scrape", json={"source": "kankai", "max_notices": 50}).status_code == 422


def test_live_source_against_mock_site(make_api, seed_dir, db_session):
    site = MockKankai()
    api = make_api(seed_dir, site)
    report = api.post("/tenders/scrape", json={"source": "kankai", "max_notices": 3}).json()
    assert report["source"] == "kankai"
    assert report["created"] == 1 and len(report["skipped"]) == 2 and report["blocked"] is None
    [tender] = db_session.scalars(select(Tender)).all()
    assert tender.source_url == BODY_URL and tender.status == "new"
    assert "लागत अनुमान: रु. ९,५०,०००/-" in tender.raw_text


def test_live_source_blocked_is_reported_not_raised(make_api, seed_dir, db_session):
    site = MockKankai(robots_status=403)
    report = make_api(seed_dir, site).post("/tenders/scrape", json={"source": "kankai"}).json()
    assert report["created"] == 0 and "robots.txt unavailable" in report["blocked"]
    assert db_session.scalars(select(Tender)).all() == []
