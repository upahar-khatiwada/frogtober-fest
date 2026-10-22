"""The routes behind the proposal page and the Runs page: a person's section edit (a new version), re-review of the
edit without the automatic revision, the attachment checklist, the PDF/DOCX downloads, the agent_runs audit list, and
the pinned demo clock. Needs Postgres (pgserver) and the fake Ollama of tests.test_review.
"""

from datetime import datetime

from sqlalchemy import select

from agents.proposal import edited_section
from agents.review import run_review
from db.models import AgentRunRow
from nepal.dates import NPT
from schemas import ProposalSection, SectionFlag, SectionFlagKind
from tests.test_matching import NOW, settings_
from tests.test_proposal import db_client
from tests.test_review import ReviewFake, drafted_001, use, versions
from tests.test_tenders_list_api import api  # noqa: F401  (fixture)

K = SectionFlagKind
WHO = {"approved_by": "Sita Demo Thapa"}


def reviewed_001(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender = drafted_001(pg_url, make_client, db_session, session_factory, ReviewFake(mention_security=True))
    run_review(db_session, db_client(session_factory, ReviewFake(mention_security=True)), tender,
               settings=settings_(), now=NOW)
    [row] = versions(db_session, tender.id)
    return tender, row


# --- edit -> new version ---------------------------------------------------------------------------------------

def test_edited_section_drops_cleared_markers_and_keeps_a_hand_written_stub_ungrounded():
    section = ProposalSection(key="team", title="Team", body="[MISSING: company.pan] and ⟦unsourced: 12345⟧",
                              cited_chunk_ids=[3], grounded=True,
                              flags=[SectionFlag(kind=K.MISSING_VALUE, detail="pan"),
                                     SectionFlag(kind=K.UNSOURCED_FIGURE, detail="12345"),
                                     SectionFlag(kind=K.GAPS_REPORTED, detail="CVs")])
    edited = edited_section(section, "PAN 301234567 and [MISSING: company.pan]", "Sita", NOW)
    assert [f.kind for f in edited.flags] == [K.MISSING_VALUE, K.GAPS_REPORTED]  # the masked figure was edited out
    assert edited.cited_chunk_ids == [3] and edited.edited_by == "Sita" and edited.body_template == edited.body
    stub = ProposalSection(key="team", title="Team", body="_No material_", grounded=False,
                           flags=[SectionFlag(kind=K.NO_KB_MATERIAL, detail="none")])
    [flag] = edited_section(stub, "Our engineer has 10 years of experience.", "Sita", NOW).flags
    assert flag.kind is K.UNGROUNDED  # written by hand, still backed by no KB chunk


def test_edit_saves_a_new_unreviewed_version_and_rereview_has_no_revision(
        api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender, v1 = reviewed_001(api, db_session, pg_url, make_client, session_factory)
    key = v1.sections[0]["key"]
    edit = {"body": "Edited by hand. A bid security is enclosed.", "edited_by": "Sita Demo Thapa", "note": "tone"}
    resp = api.post(f"/proposals/{v1.id}/sections/{key}/edit", json=edit)
    assert resp.status_code == 201, resp.text
    v2 = resp.json()
    assert v2["version"] == 2 and v2["status"] == "draft" and v2["review"] is None
    assert v2["sections"][0]["body"] == edit["body"] and v2["sections"][0]["edited_by"] == "Sita Demo Thapa"
    assert v2["sections"][1:] == api.get(f"/proposals/{v1.id}").json()["sections"][1:]  # the rest copied
    assert api.get(f"/proposals/{v1.id}").json()["sections"][0]["body"] != edit["body"]  # v1 untouched
    [audit] = db_session.scalars(select(AgentRunRow).where(AgentRunRow.tender_id == tender.id,
                                                          AgentRunRow.model == "human")).all()
    assert audit.stage == "proposal" and audit.output_json["action"] == "edit" and audit.output_json["section"] == key

    # The old version is no longer approvable (a newer one exists), the new one not until reviewed.
    api.post(f"/proposals/{v1.id}/open")
    assert "newer" in api.post(f"/proposals/{v1.id}/approve", json=WHO).json()["detail"]
    assert "not been reviewed" in api.post(f"/proposals/{v2['id']}/approve", json=WHO).json()["detail"]
    # Editing an older version, an unknown section, an unchanged text, or a bad body is refused.
    assert api.post(f"/proposals/{v1.id}/sections/{key}/edit", json=edit).status_code == 409
    assert api.post(f"/proposals/{v2['id']}/sections/nope/edit", json=edit).status_code == 404
    assert api.post(f"/proposals/{v2['id']}/sections/{key}/edit", json=edit).status_code == 409
    assert api.post(f"/proposals/{v2['id']}/sections/{key}/edit", json={**edit, "body": ""}).status_code == 422
    assert api.post("/proposals/99999/sections/x/edit", json=edit).status_code == 404

    # Re-review: Review only, never a revision, even on needs_work (the model must not rewrite a person's text).
    fake = ReviewFake(gaps=[{"section_key": key, "issue": "Too short", "severity": "hard"}], mention_security=True)
    use(api, fake)
    assert api.post(f"/proposals/{v1.id}/review").status_code == 409  # not the latest
    resp = api.post(f"/proposals/{v2['id']}/review")
    assert resp.status_code == 202, resp.text
    run = api.get(f"/runs/{resp.json()['id']}").json()
    assert run["status"] == "succeeded" and [s["stage"] for s in run["stages"]] == ["review"]
    assert fake.revisions == [] and len(versions(db_session, tender.id)) == 2
    reviewed = api.get(f"/proposals/{v2['id']}").json()
    assert reviewed["review"]["verdict"] == "needs_work" and reviewed["status"] == "reviewed"
    assert api.post(f"/proposals/{v2['id']}/review").status_code == 409  # already reviewed
    api.post(f"/proposals/{v2['id']}/open")
    assert api.post(f"/proposals/{v2['id']}/approve", json=WHO).status_code == 200  # needs_work is approvable
    assert api.post(f"/proposals/{v2['id']}/sections/{key}/edit",
                    json={**edit, "body": "After approval"}).status_code == 409  # approved is final


# --- checklist and downloads -----------------------------------------------------------------------------------

def test_checklist_before_approval_and_downloads_after(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    _, row = reviewed_001(api, db_session, pg_url, make_client, session_factory)
    resp = api.get(f"/proposals/{row.id}/checklist")
    assert resp.status_code == 200, resp.text
    by_type = {r["doc_type"]: r for r in resp.json()}
    assert by_type["tax_clearance"]["status"] == "missing" and "2081/82" in by_type["tax_clearance"]["note"]
    assert api.get("/proposals/99999/checklist").status_code == 404

    assert api.get(f"/proposals/{row.id}/export/pdf").status_code == 409  # not approved
    api.post(f"/proposals/{row.id}/open")
    assert api.post(f"/proposals/{row.id}/approve", json=WHO).status_code == 200
    pdf = api.get(f"/proposals/{row.id}/export/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and ".pdf" in pdf.headers["content-disposition"]
    docx = api.get(f"/proposals/{row.id}/export/docx")
    assert docx.status_code == 200 and docx.content.startswith(b"PK") and ".docx" in docx.headers["content-disposition"]
    assert api.get(f"/proposals/{row.id}/export/zip").status_code == 422


# --- the audit log ---------------------------------------------------------------------------------------------

def test_agent_runs_lists_every_row_newest_first_with_filters(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender, row = reviewed_001(api, db_session, pg_url, make_client, session_factory)
    api.post(f"/proposals/{row.id}/open")
    api.post(f"/proposals/{row.id}/approve", json=WHO)
    rows = api.get("/agent-runs", params={"limit": 200}).json()
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids, reverse=True) and len(rows) == db_session.query(AgentRunRow).count()
    first = rows[0]
    assert first["model"] == "human" and first["stage"] == "review" and first["output_json"]["action"] == "approve"
    assert first["tender_title"] and first["input_hash"] and len(first["input_hash"]) == 64
    reviews = api.get("/agent-runs", params={"stage": "review", "tender_id": tender.id}).json()
    assert reviews and {r["stage"] for r in reviews} == {"review"}
    assert api.get("/agent-runs", params={"ok": "false"}).json() == []
    assert len(api.get("/agent-runs", params={"limit": 2}).json()) == 2
    assert api.get("/agent-runs", params={"stage": "bogus"}).status_code == 422


# --- demo clock ------------------------------------------------------------------------------------------------

def test_demo_now_pins_the_api_clock(monkeypatch):
    from config import get_settings
    from deps import get_now

    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_NOW", "2026-10-22T04:15:00+00:00")
    try:
        assert get_now() == datetime(2026, 10, 22, 10, 0, tzinfo=NPT)
        monkeypatch.delenv("DEMO_NOW")
        get_settings.cache_clear()
        assert abs((get_now() - datetime.now(NPT)).total_seconds()) < 5
    finally:
        get_settings.cache_clear()



def test_empty_demo_now_means_real_time(monkeypatch):
    from config import Settings

    monkeypatch.setenv("DEMO_NOW", "")  # what docker-compose passes when DEMO_NOW is not set
    assert Settings().demo_now is None
