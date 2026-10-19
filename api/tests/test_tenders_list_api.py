"""GET /tenders (ranking, filters, AD+BS deadline), GET /tenders/{id}, POST /tenders/{id}/analyze (needs Postgres)."""

from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.scout import apply_record
from config import get_settings
from db.models import Match, Tender
from deps import get_llm_client, get_now, get_session, get_sessionmaker
from main import app
from nepal.dates import NPT
from pipeline.llm import LLMClient
from schemas import MatchAssessment, MatchResult
from tests.conftest import FakeOllama, bag_of_words_vector
from tests.test_matching import COMPANY, NOW, assessment_json, record, seed_company, settings_


@pytest.fixture
def api(session_factory):
    holder = {}

    def session():
        with session_factory() as s:
            yield s

    def client_dep():
        yield holder["llm"]

    app.dependency_overrides.update({
        get_session: session, get_sessionmaker: lambda: session_factory, get_now: lambda: NOW,
        get_llm_client: client_dep, get_settings: lambda: settings_(),
    })
    with TestClient(app) as client:
        client.holder = holder
        yield client
    app.dependency_overrides.clear()


def add(session, url: str, *, score: int | None = None, status: str | None = None, **over) -> Tender:
    tender = Tender(source_url=url, raw_text=f"notice {url}")
    apply_record(tender, record(title=f"Tender {url}", **over))
    if score is None:
        tender.status = status or "extracted"
    else:
        result = MatchResult.from_assessment(MatchAssessment(score=score, reasons=[f"score {score}"]), threshold=60)
        tender.status = status or ("matched" if result.decision.value == "pursue" else "skipped")
    session.add(tender)
    session.flush()
    if score is not None:
        session.add(Match(tender_id=tender.id, score=result.score, reasons=result.model_dump(mode="json"),
                          decision=result.decision.value))
    session.commit()
    return tender


@pytest.fixture
def seeded(db_session):
    d = lambda days: NOW + timedelta(days=days)  # noqa: E731
    return {
        "a": add(db_session, "a", score=90, deadline_ad=d(40)),
        "b": add(db_session, "b", score=90, deadline_ad=d(10), method="quotation", language="ne"),
        "c": add(db_session, "c", score=70, deadline_ad=d(5), district="Kaski", buyer_level="province"),
        "d": add(db_session, "d", score=30, deadline_ad=d(3), procurement_type="goods", district="Jhapa", province="koshi"),
        "e": add(db_session, "e", deadline_ad=d(1)),  # not matched yet
        "f": add(db_session, "f", score=95, deadline_ad=d(-2), language="mixed"),  # passed
        "g": add(db_session, "g", score=80, deadline_ad=None, district=None, province=None),
    }


def ids(resp, seeded) -> list[str]:
    by_id = {t.id: k for k, t in seeded.items()}
    assert resp.status_code == 200, resp.text
    return [by_id[row["id"]] for row in resp.json()]


def test_ranked_by_score_then_deadline_unscored_last(api, seeded):
    resp = api.get("/tenders")
    assert ids(resp, seeded) == ["f", "b", "a", "g", "c", "d", "e"]
    assert [row["rank"] for row in resp.json()] == list(range(1, 8))
    e = resp.json()[-1]
    assert e["score"] is None and e["decision"] is None and e["reasons"] == []


def test_deadline_in_ad_and_bs_with_days_left(api, db_session):
    tender = add(db_session, "x", score=80, deadline_ad=datetime(2026, 11, 21, 12, 0, tzinfo=NPT))
    [row] = api.get("/tenders").json()
    assert row["id"] == tender.id
    dl = row["deadline"]
    assert dl["ad_date"] == "2026-11-21" and dl["ad"].startswith("2026-11-21T12:00:00+05:45")
    assert dl["bs"] == "2083-08-05" and dl["bs_long"] == "5 Mangsir 2083"
    assert dl["bs_ne"] == "५ मंसिर २०८३"
    assert dl["days_left"] == 33 and dl["passed"] is False


def test_passed_deadline_and_missing_deadline(api, seeded):
    rows = {r["id"]: r for r in api.get("/tenders").json()}
    assert rows[seeded["f"].id]["deadline"]["passed"] is True and rows[seeded["f"].id]["deadline"]["days_left"] == -2
    assert rows[seeded["g"].id]["deadline"] is None


@pytest.mark.parametrize("query, expected", [
    ("procurement_type=goods", ["d"]),
    ("method=quotation", ["b"]),
    ("province=koshi", ["d"]),
    ("district=Kaski", ["c"]),
    ("district=kaski", ["c"]),
    ("district=तनहुँ", ["f", "b", "a", "e"]),
    ("buyer_level=province", ["c"]),
    ("min_score=80", ["f", "b", "a", "g"]),
    ("deadline_within_days=7", ["c", "d", "e"]),
    ("deadline_within_days=10", ["b", "c", "d", "e"]),
    ("language=ne", ["b"]),
    ("language=mixed", ["f"]),
    ("decision=skip", ["d"]),
    ("status=extracted", ["e"]),
    ("procurement_type=works&min_score=75&deadline_within_days=30", ["b"]),
])
def test_filters(api, seeded, query, expected):
    assert ids(api.get(f"/tenders?{query}"), seeded) == expected


def test_deadline_within_days_excludes_passed_and_unknown(api, seeded):
    got = ids(api.get("/tenders?deadline_within_days=365"), seeded)
    assert "f" not in got and "g" not in got


@pytest.mark.parametrize("query", ["procurement_type=food", "province=gandaki_x", "min_score=101", "deadline_within_days=-1",
                                   "buyer_level=ward", "language=hi"])
def test_bad_filter_values_are_422(api, seeded, query):
    assert api.get(f"/tenders?{query}").status_code == 422


def test_pagination_keeps_rank(api, seeded):
    rows = api.get("/tenders?limit=2&offset=2").json()
    assert [r["rank"] for r in rows] == [3, 4] and [r["id"] for r in rows] == [seeded["a"].id, seeded["g"].id]


def test_get_tender_detail(api, seeded):
    body = api.get(f"/tenders/{seeded['a'].id}").json()
    assert body["status"] == "matched" and body["match"]["score"] == 90
    assert body["record"]["title"] == "Tender a" and body["deadline_view"]["days_left"] == 40
    assert api.get("/tenders/99999").status_code == 404


def make_llm(fake: FakeOllama) -> LLMClient:
    return LLMClient(lambda _run: None, settings_(), transport=httpx.MockTransport(fake.handler))


def test_analyze_runs_matching_and_ranks(api, db_session):
    seed_company(db_session)
    good = add(db_session, "good", deadline_ad=NOW + timedelta(days=30))
    off = add(db_session, "off", deadline_ad=NOW + timedelta(days=30), district="Jumla", province="karnali")
    api.holder["llm"] = make_llm(FakeOllama([assessment_json(85)], embed_fn=bag_of_words_vector))
    for t in (good, off):  # 202: a background run (TestClient runs it before returning)
        resp = api.post(f"/tenders/{t.id}/analyze")
        assert resp.status_code == 202 and resp.json()["status"] == "queued", resp.text
    r1, r2 = (api.get(f"/tenders/{t.id}") for t in (good, off))
    # Pursued -> Compliance runs. This fixture KB has only an experience certificate, so the rules hard-fail it.
    assert r1.json()["match"]["decision"] == "pursue"
    assert r1.json()["status"] == "blocked" and r1.json()["compliance"]["blocked"] is True
    assert r2.json()["status"] == "skipped" and "Jumla" in r2.json()["match"]["skip_reasons"][0]
    assert r2.json()["compliance"] is None  # a skipped tender never reaches Compliance
    rows = api.get("/tenders").json()
    assert [r["id"] for r in rows] == [good.id, off.id]
    assert rows[0]["reasons"][-1].startswith("[model] ")
    assert rows[0]["hard_failures"] >= 1 and rows[1]["hard_failures"] is None


def test_analyze_conflicts(api, db_session):
    seed_company(db_session)
    new = Tender(source_url="new", raw_text="x", status="new")
    drafted = Tender(source_url="drafted", raw_text="x", status="drafted")
    db_session.add_all([new, drafted])
    db_session.commit()
    api.holder["llm"] = make_llm(FakeOllama([]))
    assert api.post(f"/tenders/{drafted.id}/analyze").status_code == 409  # proposal work exists; needs from_stage
    assert api.post(f"/tenders/{new.id}/analyze", json={"target": "approved"}).status_code == 409  # human-only
    assert api.post(f"/tenders/{new.id}/analyze", json={"target": "drafted"}).status_code == 409  # no Proposal agent yet
    assert api.post(f"/tenders/{new.id}/analyze", json={"from_stage": "matching"}).status_code == 409  # not extracted
    assert api.post(f"/tenders/{new.id}/analyze", json={"bogus": 1}).status_code == 422
    assert api.post("/tenders/99999/analyze").status_code == 404


def test_company_profile_round_trips_procurement_types(api):
    resp = api.post("/company", json=COMPANY.model_dump(mode="json"))
    assert resp.status_code == 200 and resp.json()["procurement_types"] == ["works"]
