"""POST /tenders/{id}/analyze -> Compliance, GET /tenders/{id} compliance section, override, proposal gate (needs Postgres)."""

import httpx

from pipeline.llm import LLMClient
from tests.conftest import FakeOllama, bag_of_words_vector
from tests.test_compliance import demo_tender, seed_demo, unclear_json
from tests.test_matching import assessment_json, settings_
from tests.test_tenders_list_api import api  # noqa: F401  (fixture)


def llm(replies: list[str]) -> LLMClient:
    return LLMClient(lambda _run: None, settings_(),
                     transport=httpx.MockTransport(FakeOllama(replies, embed_fn=bag_of_words_vector).handler))


def blocked_001(api, db_session, pg_url, make_client):  # noqa: F811
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="extracted")
    api.holder["llm"] = llm([assessment_json(85)] + [unclear_json()] * 3)
    resp = api.post(f"/tenders/{tender.id}/analyze")
    assert resp.status_code == 202, resp.text
    run = api.get(f"/runs/{resp.json()['id']}").json()
    assert run["status"] == "stopped" and run["end_status"] == "blocked", run
    return tender, api.get(f"/tenders/{tender.id}").json()


def test_analyze_then_detail_shows_compliance(api, db_session, pg_url, make_client):  # noqa: F811
    tender, body = blocked_001(api, db_session, pg_url, make_client)
    assert body["status"] == "blocked" and body["match"]["decision"] == "pursue"
    comp = body["compliance"]
    assert comp["blocked"] is True and comp["hard_failures"] == 1 and comp["proposal_allowed"] is False
    assert comp["override"] is None and sum(comp["counts"].values()) == len(comp["items"])
    tax = next(i for i in comp["items"] if i["rule_id"] == "NP-TAX-CLEARANCE")
    assert (tax["status"], tax["severity"], tax["source"]) == ("fail", "hard", "rule")
    assert tax["action_needed"].startswith("Renew tax clearance for F/Y 2082/83") and tax["evidence_document_ids"]
    assert {i["source"] for i in comp["items"]} == {"rule", "model"}
    assert api.get(f"/tenders/{tender.id}").json()["compliance"] == comp
    [row] = [r for r in api.get("/tenders").json() if r["id"] == tender.id]
    assert row["status"] == "blocked" and row["hard_failures"] == 1


def test_proposal_refused_while_blocked_then_override(api, db_session, pg_url, make_client):  # noqa: F811
    tender, _ = blocked_001(api, db_session, pg_url, make_client)
    resp = api.post(f"/tenders/{tender.id}/proposal")
    assert resp.status_code == 409 and f"/tenders/{tender.id}/compliance/override" in resp.json()["detail"]

    assert api.post(f"/tenders/{tender.id}/compliance/override", json={}).status_code == 422
    assert api.post(f"/tenders/{tender.id}/compliance/override", json={"overridden_by": " ", "reason": "x"}).status_code == 422
    resp = api.post(f"/tenders/{tender.id}/compliance/override",
                    json={"overridden_by": "Sita Demo Thapa", "reason": "FY 2082/83 clearance issued; upload pending."})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "checked"
    override = body["compliance"]["override"]
    assert override["overridden_by"] == "Sita Demo Thapa" and override["active"] is True and override["overridden_at"]
    assert override["hard_failures"] == ["NP-TAX-CLEARANCE:Tax clearance for F/Y 2082/83"]
    assert body["compliance"]["blocked"] is True and body["compliance"]["proposal_allowed"] is True
    # Gate passes; the proposal stage itself is still a stub.
    assert api.post(f"/tenders/{tender.id}/proposal").status_code == 501
    # A second override is refused: the tender is no longer blocked.
    assert api.post(f"/tenders/{tender.id}/compliance/override",
                    json={"overridden_by": "x", "reason": "y"}).status_code == 409


def test_override_and_proposal_errors(api, db_session, pg_url, make_client):  # noqa: F811
    assert api.post("/tenders/99999/compliance/override", json={"overridden_by": "x", "reason": "y"}).status_code == 404
    assert api.post("/tenders/99999/proposal").status_code == 404
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="extracted")
    assert api.post(f"/tenders/{tender.id}/proposal").status_code == 409  # not checked yet
    assert api.post(f"/tenders/{tender.id}/compliance/override", json={"overridden_by": "x", "reason": "y"}).status_code == 409
