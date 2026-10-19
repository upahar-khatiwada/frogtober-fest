"""POST /tenders/{id}/analyze (202, background run), GET /runs/{id} polling, GET /runs list (needs Postgres)."""

from datetime import UTC, datetime, timedelta

import httpx

from db.models import PipelineRun
from db.runs import make_run_recorder
from pipeline.llm import LLMClient
from tests.conftest import FakeOllama, bag_of_words_vector
from tests.test_matching import assessment_json, seed_company, settings_
from tests.test_tenders_list_api import add, api  # noqa: F401  (fixture)


def llm(session_factory, replies: list[str]) -> LLMClient:
    return LLMClient(make_run_recorder(session_factory), settings_(),
                     transport=httpx.MockTransport(FakeOllama(replies, embed_fn=bag_of_words_vector).handler))


def test_analyze_returns_queued_run_then_poll_shows_stages(api, db_session, session_factory):  # noqa: F811
    seed_company(db_session)
    tender = add(db_session, "good")
    api.holder["llm"] = llm(session_factory, [assessment_json(85)])
    resp = api.post(f"/tenders/{tender.id}/analyze")
    assert resp.status_code == 202
    queued = resp.json()
    assert (queued["status"], queued["start_status"], queued["target"]) == ("queued", "extracted", "checked")
    assert [(s["stage"], s["status"]) for s in queued["stages"]] == [("matching", "pending"), ("compliance", "pending")]

    run = api.get(f"/runs/{queued['id']}").json()
    assert run["status"] == "stopped" and run["end_status"] == "blocked" and run["tender_title"] == "Tender good"
    assert [(s["stage"], s["status"], s["to_status"]) for s in run["stages"]] == [
        ("matching", "ok", "matched"), ("compliance", "branched", "blocked")]
    assert all(isinstance(s["duration_ms"], int) for s in run["stages"]) and run["duration_ms"] >= 0
    stages = {r["stage"] for r in run["agent_runs"]}
    assert stages == {"matching", "compliance"}
    assert all(r["pipeline_run_id"] == run["id"] and r["cached"] is False for r in run["agent_runs"])
    assert api.get(f"/tenders/{tender.id}").json()["status"] == "blocked"


def test_failed_run_then_resume_via_api(api, db_session, session_factory):  # noqa: F811
    seed_company(db_session)
    tender = add(db_session, "t")
    api.holder["llm"] = llm(session_factory, ['{"score": "high"}', '{"score": "high"}'])
    first = api.get(f"/runs/{api.post(f'/tenders/{tender.id}/analyze').json()['id']}").json()
    assert first["status"] == "failed" and first["end_status"] == "failed" and first["error"].startswith("matching:")
    assert [s["status"] for s in first["stages"]] == ["failed", "not_run"]
    assert [r["ok"] for r in first["agent_runs"]] == [False]

    api.holder["llm"] = llm(session_factory, [assessment_json(85)])
    second = api.get(f"/runs/{api.post(f'/tenders/{tender.id}/analyze').json()['id']}").json()
    assert second["resumed_from"] == "failed" and second["stages"][0]["from_status"] == "extracted"
    assert second["end_status"] == "blocked"


def test_list_runs_newest_first_with_filters(api, db_session, session_factory):  # noqa: F811
    seed_company(db_session)
    a = add(db_session, "a")
    b = add(db_session, "b", district="Jumla", province="karnali")  # hard skip: no model call
    api.holder["llm"] = llm(session_factory, [assessment_json(85)])
    ids = [api.post(f"/tenders/{t.id}/analyze").json()["id"] for t in (a, b)]
    rows = api.get("/runs").json()
    assert [r["id"] for r in rows] == ids[::-1]
    assert [r["id"] for r in api.get("/runs", params={"tender_id": a.id}).json()] == [ids[0]]
    assert [r["id"] for r in api.get("/runs", params={"status": "stopped"}).json()] == ids[::-1]
    assert api.get("/runs", params={"status": "running"}).json() == []
    assert [r["id"] for r in api.get("/runs", params={"limit": 1, "offset": 1}).json()] == [ids[0]]
    assert "agent_runs" not in rows[0]
    assert api.get("/runs", params={"status": "bogus"}).status_code == 422


def test_run_404_and_active_run_409(api, db_session, session_factory):  # noqa: F811
    assert api.get("/runs/99999").status_code == 404
    api.holder["llm"] = llm(session_factory, [])
    seed_company(db_session)
    tender = add(db_session, "busy")
    db_session.add(PipelineRun(tender_id=tender.id, target="checked", status="running", start_status="extracted"))
    db_session.commit()
    resp = api.post(f"/tenders/{tender.id}/analyze")
    assert resp.status_code == 409 and "active run" in resp.json()["detail"]


def test_polling_reaps_a_run_whose_worker_died(api, db_session, session_factory):  # noqa: F811
    seed_company(db_session)
    api.holder["llm"] = llm(session_factory, [assessment_json(85)])
    tender = add(db_session, "dead")
    run = PipelineRun(tender_id=tender.id, target="checked", status="running", start_status="extracted",
                      stages=[{"stage": "matching", "status": "running", "from_status": "extracted"}],
                      heartbeat_at=datetime.now(UTC) - timedelta(hours=2))
    db_session.add(run)
    db_session.commit()
    body = api.get(f"/runs/{run.id}").json()
    assert body["status"] == "failed" and body["error"].startswith("interrupted")
    assert body["stages"][0]["status"] == "failed"
    # the tender is free to run again
    assert api.post(f"/tenders/{tender.id}/analyze", json={"target": "matched"}).status_code == 202
