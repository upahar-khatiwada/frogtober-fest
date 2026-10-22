"""Review agent: deterministic checks, verdict logic, the narrowed model schema, the revision pass, the human gate.

Pure tests need nothing; DB/API tests need Postgres (pgserver) and a fake Ollama that drafts (tests.test_proposal) and
reviews with scripted scores.
"""

import json
from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from agents.proposal import run_proposal
from agents.review import (BID_SECURITY, assessment_schema, build_messages, decide_verdict, review_proposal,
                           revision_feedback, run_checks, run_review)
from db.models import AgentRunRow, ProposalRow, Tender
from pipeline.llm import LLMClient, LLMOutputError
from pipeline.orchestrator import resume_status, run_pipeline
from schemas import (GapSource, ProposalSection, Requirement, ReviewCheck, ReviewCheckId, ReviewGap, ReviewScores,
                     ReviewVerdict, SectionFlag, Severity, Stage, TenderStatus)
from tests.conftest import FakeOllama
from tests.test_matching import NOW, record, settings_
from tests.test_proposal import DraftFake, checked_001, db_client
from tests.test_tenders_list_api import api  # noqa: F401  (fixture)

C, V = ReviewCheckId, ReviewVerdict
HARD, SOFT = Severity.HARD, Severity.SOFT


def req(text: str, category: str = "eligibility", mandatory: bool = True) -> Requirement:
    return Requirement(text=text, mandatory=mandatory, category=category, source_quote=text)


def sec(key: str, body: str = "Text.", *, reqs=(), cited=(1,), flags=()) -> ProposalSection:
    return ProposalSection(key=key, title=key.replace("_", " ").capitalize(), body=body, cited_chunk_ids=list(cited),
                           grounded=bool(cited), requirement_indices=list(reqs),
                           flags=[SectionFlag(kind=k, detail="x") for k in flags])


REQS = [req("Class D or above construction licence"), req("One similar road contract", "experience"),
        req("ISO 9001 certificate", "other", mandatory=False)]
GOOD = [sec("cover_letter", "We submit our bid."), sec("bidder_info", "Licence class C.", reqs=[0]),
        sec("relevant_experience", "Vyas road.", reqs=[1]),
        sec("declarations", "A bid security of Rs 4,46,000 is enclosed.")]


def rec(**over):
    return record(requirements=REQS, bid_security={"amount_npr": 446000}, **over)


def by_check(checks) -> dict[ReviewCheckId, ReviewCheck]:
    return {c.check: c for c in checks}


SCORES = ReviewScores(completeness=85, relevance=80, compliance=90)


# --- deterministic checks ---------------------------------------------------------------------------------------

def test_a_complete_proposal_passes_every_check():
    checks, gaps = run_checks(rec(), GOOD, NOW)
    assert all(c.passed for c in checks) and gaps == []
    assert [c.check for c in checks] == [C.MANDATORY_ADDRESSED, C.NO_PLACEHOLDERS, C.BID_SECURITY_STATED,
                                        C.DEADLINE_NOT_PASSED, C.SECTIONS_CITED]
    assert by_check(checks)[C.MANDATORY_ADDRESSED].detail == "2 of 2 mandatory requirements answered"


def test_mandatory_requirement_in_a_stub_section_is_unanswered_and_hard():
    sections = [*GOOD[:2], sec("relevant_experience", "_No material._", reqs=[1], cited=(), flags=["no_kb_material"]),
                GOOD[3]]
    checks, gaps = run_checks(rec(), sections, NOW)
    check = by_check(checks)[C.MANDATORY_ADDRESSED]
    assert not check.passed and check.severity is HARD
    [gap] = [g for g in gaps if g.check is C.MANDATORY_ADDRESSED]
    assert (gap.requirement_index, gap.section_key, gap.severity) == (1, "relevant_experience", HARD)
    assert "One similar road contract" in gap.issue and "no knowledge-base material" in gap.issue


def test_unrouted_mandatory_requirement_and_optional_ones():
    sections = [sec("cover_letter"), sec("bidder_info", reqs=[0]), sec("declarations", "Bid security enclosed.")]
    checks, gaps = run_checks(rec(), sections, NOW)
    [gap] = [g for g in gaps if g.check is C.MANDATORY_ADDRESSED]  # requirement 2 is optional: not required
    assert gap.requirement_index == 1 and gap.section_key is None and "no section answers it" in gap.issue


@pytest.mark.parametrize("marker", ["[MISSING: company.vat]", "[UNKNOWN: fact.road]", "[UNVERIFIED: fact.a]",
                                    "⟦unsourced: Rs 12,00,000⟧", "{{company.pan}}", "[insert signatory name]", "TBD",
                                    "XXXX"])
def test_unresolved_placeholders_are_a_soft_gap_per_section(marker):
    sections = [*GOOD[:2], sec("relevant_experience", f"Road worth {marker}.", reqs=[1]), GOOD[3]]
    checks, gaps = run_checks(rec(), sections, NOW)
    assert not by_check(checks)[C.NO_PLACEHOLDERS].passed
    [gap] = gaps
    assert (gap.check, gap.section_key, gap.severity) == (C.NO_PLACEHOLDERS, "relevant_experience", SOFT)
    assert marker in gap.issue


def test_ordinary_brackets_are_not_placeholders():
    sections = [*GOOD[:3], sec("declarations", "Bid security enclosed [see annex 2]; ward [5] road; 3 tippers.")]
    assert by_check(run_checks(rec(), sections, NOW)[0])[C.NO_PLACEHOLDERS].passed


def test_bid_security_must_be_stated_when_the_notice_asks():
    sections = [*GOOD[:3], sec("declarations", "We are not blacklisted.")]
    checks, gaps = run_checks(rec(), sections, NOW)
    assert not by_check(checks)[C.BID_SECURITY_STATED].passed
    [gap] = gaps
    assert gap.section_key == "declarations" and "Rs 4,46,000" in gap.suggestion and gap.severity is SOFT
    # No bid security in the notice: nothing to state.
    assert by_check(run_checks(record(requirements=REQS), sections, NOW)[0])[C.BID_SECURITY_STATED].passed
    # A required bid-security document counts as "asks for one" too; Nepali wording counts as stated.
    assert BID_SECURITY.search("रु. ४,४६,००० को धरौटी संलग्न छ") and BID_SECURITY.search("बोलपत्र जमानत")


def test_deadline_passed_is_hard_and_unknown_is_soft():
    passed = by_check(run_checks(rec(deadline_ad=NOW - timedelta(minutes=1)), GOOD, NOW)[0])[C.DEADLINE_NOT_PASSED]
    assert not passed.passed and passed.severity is HARD and "has passed" in passed.detail and "BS" in passed.detail
    unknown = by_check(run_checks(rec(deadline_ad=None), GOOD, NOW)[0])[C.DEADLINE_NOT_PASSED]
    assert not unknown.passed and unknown.severity is SOFT


def test_uncited_sections_are_listed_as_gaps():
    sections = [*GOOD[:3], sec("declarations", "Bid security enclosed.", cited=())]
    checks, gaps = run_checks(rec(), sections, NOW)
    assert not by_check(checks)[C.SECTIONS_CITED].passed
    assert [(g.check, g.section_key) for g in gaps] == [(C.SECTIONS_CITED, "declarations")]


# --- verdict ----------------------------------------------------------------------------------------------------

def check(cid: ReviewCheckId, passed: bool, severity: Severity = SOFT) -> ReviewCheck:
    return ReviewCheck(check=cid, passed=passed, severity=severity, detail="d")


def model_gap(severity: Severity) -> ReviewGap:
    return ReviewGap(source=GapSource.MODEL, section_key="work_plan", issue="i", severity=severity)


OK = [check(C.MANDATORY_ADDRESSED, True, HARD), check(C.NO_PLACEHOLDERS, True)]


@pytest.mark.parametrize("scores, checks, gaps, verdict", [
    ((85, 80, 90), OK, [], V.PASS),
    ((70, 70, 70), OK, [], V.PASS),  # inclusive pass threshold
    ((69, 90, 90), OK, [], V.NEEDS_WORK),
    ((85, 80, 90), OK + [check(C.NO_PLACEHOLDERS, False)], [], V.NEEDS_WORK),
    ((85, 80, 90), OK, [model_gap(SOFT)], V.PASS),
    ((85, 80, 90), OK, [model_gap(HARD)], V.NEEDS_WORK),  # the model alone cannot fail a proposal on a gap
    ((39, 90, 90), OK, [], V.FAIL),
    ((40, 90, 90), OK, [], V.NEEDS_WORK),  # 40 is not below 40
    ((95, 95, 95), [check(C.DEADLINE_NOT_PASSED, False, HARD)], [], V.FAIL),
    ((95, 95, 95), [check(C.MANDATORY_ADDRESSED, False, HARD)], [], V.FAIL),
])
def test_verdict_is_computed_in_code(scores, checks, gaps, verdict):
    s = ReviewScores(completeness=scores[0], relevance=scores[1], compliance=scores[2])
    got, reasons = decide_verdict(s, checks, gaps, pass_min=70, fail_below=40)
    assert got is verdict and reasons
    assert all(r.startswith(("[check]", "[model]")) for r in reasons) or got is V.PASS


# --- the model call ---------------------------------------------------------------------------------------------

def test_assessment_schema_only_allows_real_sections_and_requirements():
    schema = assessment_schema(["cover_letter", "work_plan"], 3)
    ok = schema.model_validate_json(json.dumps({"scores": {"completeness": 80, "relevance": 80, "compliance": 80},
                                                "gaps": [{"section_key": "work_plan", "requirement_index": 2,
                                                          "issue": "x", "severity": "soft"}]}), strict=True)
    assert ok.gaps[0].section_key == "work_plan"
    for gap in ({"section_key": "team", "issue": "x", "severity": "soft"},
                {"requirement_index": 3, "issue": "x", "severity": "soft"},
                {"issue": "untied", "severity": "soft"}):
        with pytest.raises(ValidationError):
            schema.model_validate_json(json.dumps({"scores": {"completeness": 1, "relevance": 1, "compliance": 1},
                                                   "gaps": [gap]}), strict=True)
    gap_schema = schema.model_json_schema()["$defs"]["ReviewGapDraft"]["properties"]
    assert gap_schema["section_key"]["anyOf"][0]["enum"] == ["cover_letter", "work_plan"]  # constrains Ollama too
    no_reqs = assessment_schema(["cover_letter"], 0)
    with pytest.raises(ValidationError):
        no_reqs.model_validate_json(json.dumps({"scores": {"completeness": 1, "relevance": 1, "compliance": 1},
                                                "gaps": [{"requirement_index": 0, "issue": "x", "severity": "soft"}]}),
                                    strict=True)


def assessment_json(scores=(85, 80, 90), gaps=()) -> str:
    return json.dumps({"scores": dict(zip(("completeness", "relevance", "compliance"), scores)), "gaps": list(gaps)})


def test_review_is_one_constrained_call_at_temperature_0(make_client):
    fake = FakeOllama([assessment_json(gaps=[{"requirement_index": 1, "section_key": "relevant_experience",
                                               "issue": "Value of the similar contract not shown", "severity": "hard",
                                               "suggestion": "Cite the completion certificate"}])])
    client = make_client(fake, runs := [])
    report = review_proposal(client, rec(), GOOD, now=NOW, settings=settings_(), tender_id=7)
    [call] = fake.requests
    assert call["body"]["options"]["temperature"] == 0 and call["body"]["format"]["title"] == "ReviewAssessment"
    user = call["body"]["messages"][1]["content"]
    assert "[R 1] (mandatory, experience) One similar road contract -> answered in: relevant_experience" in user
    assert "### declarations: Declarations (cites the knowledge base: yes)" in user
    assert [(r.stage, r.ok, r.tender_id) for r in runs] == [(Stage.REVIEW, True, 7)]
    [gap] = report.gaps
    assert gap.source is GapSource.MODEL and gap.check is None and gap.requirement_index == 1
    assert report.verdict is V.NEEDS_WORK and report.verdict_reasons == ["[model] 1 hard gap(s) reported"]
    assert report.scores == SCORES and report.pass_min_score == 70 and report.uncited_sections == []


def test_prompt_withholds_nothing_code_checks_and_truncates_long_sections():
    long = [*GOOD[:3], sec("declarations", "Bid security enclosed. " + "x" * 5000)]
    system, user = (m["content"] for m in build_messages(rec(), long))
    assert "do not report them" in system and len(user) < 3000


def test_invalid_review_output_twice_raises(make_client):
    client = make_client(FakeOllama(['{"scores": 5}', assessment_json(gaps=[{"section_key": "team", "issue": "x",
                                                                             "severity": "soft"}])]), runs := [])
    with pytest.raises(LLMOutputError):  # "team" is not a section of this proposal: invalid, retried, then failed
        review_proposal(client, rec(), GOOD, now=NOW, settings=settings_())
    assert [r.ok for r in runs] == [False] and runs[0].attempts == 2


def test_revision_feedback_goes_to_the_section_that_answers_the_requirement():
    sections = GOOD
    report_gaps = [ReviewGap(source=GapSource.MODEL, requirement_index=1, issue="Value missing", severity=HARD,
                             suggestion="Cite it"),
                   ReviewGap(source=GapSource.CHECK, check=C.DEADLINE_NOT_PASSED, issue="Deadline passed", severity=HARD),
                   ReviewGap(source=GapSource.CHECK, check=C.BID_SECURITY_STATED, section_key="declarations",
                             issue="No bid security", severity=SOFT)]
    from schemas import ReviewReport
    report = ReviewReport(scores=SCORES, gaps=report_gaps, verdict=V.FAIL)
    assert revision_feedback(report, sections) == {"relevant_experience": ["Value missing Fix: Cite it"],
                                                   "declarations": ["No bid security"]}


# --- DB: run_review, the revision pass, failure + resume -------------------------------------------------------

class ReviewFake(DraftFake):
    """DraftFake that also answers ReviewAssessment with scripted scores/gaps and can mention the bid security."""

    def __init__(self, *, scores=(85, 80, 90), gaps=(), invalid_review=False, mention_security=False, **kw):
        super().__init__(**kw)
        self.scores, self.gaps = scores, list(gaps)
        self.invalid_review, self.mention_security = invalid_review, mention_security
        self.reviews: list[str] = []
        self.revisions: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/api/chat" and body["format"]["title"] == "ReviewAssessment":
            self.reviews.append(body["messages"][1]["content"])
            content = '{"scores": 1}' if self.invalid_review else assessment_json(self.scores, self.gaps)
            return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})
        return super().handler(request)

    def _draft(self, user: str) -> str:
        if "REVIEWER FEEDBACK ON THE PREVIOUS DRAFT" in user:
            self.revisions.append(user)
        draft = json.loads(super()._draft(user))
        if self.mention_security:
            draft["body"] += " A bid security of {{tender.bid_security}} is enclosed."
        return json.dumps(draft)


def drafted_001(pg_url, make_client, db_session, session_factory, fake) -> Tender:
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    run_proposal(db_session, db_client(session_factory, fake), tender, settings=settings_(), now=NOW)
    assert tender.status == "drafted"
    return tender


def versions(session, tender_id) -> list[ProposalRow]:
    return session.scalars(select(ProposalRow).where(ProposalRow.tender_id == tender_id).order_by(ProposalRow.version)).all()


def test_review_pass_stores_report_and_sets_reviewed(pg_url, make_client, db_session, session_factory):
    fake = ReviewFake(mention_security=True)
    tender = drafted_001(pg_url, make_client, db_session, session_factory, fake)
    report = run_review(db_session, db_client(session_factory, fake), tender, settings=settings_(), now=NOW)
    assert report.verdict is V.PASS and tender.status == "reviewed" and fake.revisions == []
    [row] = versions(db_session, tender.id)  # no revision on pass
    assert row.status == "reviewed" and row.reviewed_at == NOW and row.review_json["verdict"] == "pass"
    rows = db_session.scalars(select(AgentRunRow).where(AgentRunRow.tender_id == tender.id,
                                                       AgentRunRow.stage == "review")).all()
    assert sorted(r.model for r in rows) == ["deterministic", "test-model"]  # checks + verdict row, model row
    [code] = [r for r in rows if r.model == "deterministic"]
    assert code.output_json["verdict"] == "pass" and len(code.output_json["checks"]) == 5


def test_needs_work_feeds_gaps_back_once_and_reviews_the_revision(pg_url, make_client, db_session, session_factory):
    fake = ReviewFake(gaps=[{"requirement_index": 9, "issue": "Equipment ownership not shown", "severity": "soft"}])
    tender = drafted_001(pg_url, make_client, db_session, session_factory, fake)  # drafts never mention bid security
    report = run_review(db_session, db_client(session_factory, fake), tender, settings=settings_(), now=NOW)
    v1, v2 = versions(db_session, tender.id)
    assert v1.review_json["verdict"] == "needs_work" and v1.status == "reviewed"
    assert {g["check"] for g in v1.review_json["gaps"]} >= {"bid_security_stated"}
    # One revision: the declarations (bid security) and key_equipment (requirement 9) sections only, with feedback.
    assert sorted(report.revised_sections) == ["declarations", "key_equipment"]
    assert report.revision_of == 1 and report.previous_verdict is V.NEEDS_WORK
    assert len(fake.revisions) == 2 and len(fake.reviews) == 2  # never a third review or a second revision
    assert any("Equipment ownership not shown" in p for p in fake.revisions)
    assert any("PREVIOUS DRAFT" in p and "{{company.name}}" in p for p in fake.revisions)
    assert v2.review_json["revision_of"] == 1 and v2.language == v1.language and tender.status == "reviewed"
    unchanged = {s["key"]: s for s in v1.sections}
    for s in v2.sections:
        if s["key"] not in report.revised_sections:
            assert s == unchanged[s["key"]]  # copied, not redrafted


def test_auto_revise_off_stops_after_the_first_review(pg_url, make_client, db_session, session_factory):
    fake = ReviewFake()
    tender = drafted_001(pg_url, make_client, db_session, session_factory, fake)
    report = run_review(db_session, db_client(session_factory, fake), tender, now=NOW,
                        settings=settings_(review_auto_revise=False))
    assert report.verdict is V.NEEDS_WORK and len(versions(db_session, tender.id)) == 1 and fake.revisions == []


def test_review_failure_fails_the_stage_then_resumes_at_review(pg_url, make_client, db_session, session_factory):
    tender = drafted_001(pg_url, make_client, db_session, session_factory, ReviewFake())
    run = run_pipeline(session_factory, db_client(session_factory, ReviewFake(invalid_review=True)), tender.id,
                       target=TenderStatus.REVIEWED, settings=settings_(), now=NOW)
    db_session.refresh(tender)
    assert run.status == "failed" and tender.status == "failed" and "review" in run.error
    [row] = versions(db_session, tender.id)
    db_session.refresh(row)
    assert row.review_json is None and row.status == "draft"  # nothing partial kept
    assert resume_status(db_session, tender) is TenderStatus.DRAFTED

    run = run_pipeline(session_factory, db_client(session_factory, ReviewFake(mention_security=True)), tender.id,
                       target=TenderStatus.REVIEWED, settings=settings_(), now=NOW)
    db_session.refresh(tender)
    assert run.status == "succeeded" and tender.status == "reviewed" and [s["stage"] for s in run.stages] == ["review"]


def test_run_review_refuses_other_statuses(pg_url, make_client, db_session, session_factory):
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    with pytest.raises(ValueError, match="drafted"):
        run_review(db_session, db_client(session_factory, ReviewFake()), tender, now=NOW)
    tender.status = "drafted"
    db_session.commit()
    with pytest.raises(ValueError, match="no proposal"):
        run_review(db_session, db_client(session_factory, ReviewFake()), tender, now=NOW)


# --- API: proposal -> review run, the approval gate --------------------------------------------------------------

def use(api, fake) -> None:  # noqa: F811
    api.holder["llm"] = LLMClient(lambda _run: None, settings_(), transport=httpx.MockTransport(fake.handler))


def test_proposal_route_runs_proposal_then_review(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    use(api, ReviewFake(mention_security=True))
    resp = api.post(f"/tenders/{tender.id}/proposal")
    assert resp.status_code == 202, resp.text
    run = api.get(f"/runs/{resp.json()['id']}").json()
    assert run["status"] == "succeeded" and run["target"] == "reviewed" and run["end_status"] == "reviewed"
    assert [s["stage"] for s in run["stages"]] == ["proposal", "review"]
    [latest] = api.get(f"/tenders/{tender.id}/proposals").json()  # pass: no revision
    assert latest["status"] == "reviewed" and latest["review"]["verdict"] == "pass" and latest["reviewed_at"]


def test_approval_gate(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender = drafted_001(pg_url, make_client, db_session, session_factory, ReviewFake(mention_security=True))
    [row] = versions(db_session, tender.id)
    who = {"approved_by": "Sita Demo Thapa", "note": "Checked against the notice."}
    resp = api.post(f"/proposals/{row.id}/approve", json=who)
    assert resp.status_code == 409 and "not been reviewed" in resp.json()["detail"]  # a draft cannot be approved

    run_review(db_session, db_client(session_factory, ReviewFake(mention_security=True)), tender, settings=settings_(),
               now=NOW)
    resp = api.post(f"/proposals/{row.id}/approve", json=who)
    assert resp.status_code == 409 and "has not been opened since its review" in resp.json()["detail"]
    assert api.post(f"/proposals/{row.id}/approve", json={"approved_by": " "}).status_code == 422
    assert api.get(f"/proposals/{row.id}/package").status_code == 409  # not approved: no package

    opened = api.post(f"/proposals/{row.id}/open")
    assert opened.status_code == 200 and opened.json()["opened_at"] is not None
    resp = api.post(f"/proposals/{row.id}/approve", json=who)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved" and body["approved_by"] == "Sita Demo Thapa" and body["approved_at"]
    db_session.refresh(tender)
    assert tender.status == "approved"
    [audit] = db_session.scalars(select(AgentRunRow).where(AgentRunRow.tender_id == tender.id,
                                                          AgentRunRow.model == "human")).all()
    assert audit.stage == "review" and audit.ok and audit.output_json["action"] == "approve"
    assert audit.output_json["approved_by"] == "Sita Demo Thapa" and audit.output_json["verdict"] == "pass"

    again = api.post(f"/proposals/{row.id}/approve", json=who)
    assert again.status_code == 409 and "already approved" in again.json()["detail"]
    use(api, ReviewFake())
    assert api.post(f"/tenders/{tender.id}/analyze", json={"from_stage": "proposal", "target": "reviewed"}).status_code == 409
    assert api.post(f"/tenders/{tender.id}/proposal").status_code == 409  # approved is final: no re-draft
    assert api.post("/proposals/99999/approve", json=who).status_code == 404
    assert api.post("/proposals/99999/open").status_code == 404


def test_fail_verdict_cannot_be_approved(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender = drafted_001(pg_url, make_client, db_session, session_factory, ReviewFake())
    report = run_review(db_session, db_client(session_factory, ReviewFake(scores=(30, 80, 80), mention_security=True)),
                        tender, settings=settings_(review_auto_revise=False), now=NOW)
    assert report.verdict is V.FAIL and report.verdict_reasons == ["[model] lowest score 30 is below 40"]
    [row] = versions(db_session, tender.id)
    api.post(f"/proposals/{row.id}/open")
    resp = api.post(f"/proposals/{row.id}/approve", json={"approved_by": "Sita Demo Thapa"})
    assert resp.status_code == 409 and "verdict is fail" in resp.json()["detail"]
    db_session.refresh(tender)
    assert tender.status == "reviewed"


def test_opening_before_the_review_does_not_count(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    tender = drafted_001(pg_url, make_client, db_session, session_factory, ReviewFake())
    [row] = versions(db_session, tender.id)
    assert api.post(f"/proposals/{row.id}/open").status_code == 200  # opened at NOW, as a draft
    run_review(db_session, db_client(session_factory, ReviewFake(mention_security=True)), tender, settings=settings_(),
               now=NOW + timedelta(hours=1))
    resp = api.post(f"/proposals/{row.id}/approve", json={"approved_by": "Sita Demo Thapa"})
    assert resp.status_code == 409 and "opened since its review" in resp.json()["detail"]
