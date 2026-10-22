"""Proposal agent: section plan, placeholders, unsourced figures, grounding flags, language, versioning, progress, API.

Pure tests need nothing; DB/API tests need Postgres (pgserver) and use a fake Ollama that cites a chunk it was shown.
"""

import json
import re
from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from agents.compliance import override_block, run_compliance
from agents.proposal import (EOI_BASE, PlannedSection, ProposalContext, TEMPLATES, UNSOURCED_MARK, build_messages,
                             build_section, can_draft, citation_rate, format_date, generate_section, mask_unsourced,
                             plan_sections, proposal_language, run_proposal, section_query, uses_bs)
from db.models import AgentRunRow, Match, ProposalRow
from db.runs import make_run_recorder
from db.search import ChunkHit
from nepal.dates import NPT
from pipeline.llm import LLMClient, LLMOutputError
from pipeline.orchestrator import resume_status, run_pipeline
from schemas import (CompanyProfile, DocType, ProposalLanguage, ProposalSection, ProposalSectionDraft, RequiredDoc,
                     Requirement, SectionFlagKind, Stage, TenderStatus)
from tests.conftest import FakeOllama, bag_of_words_vector
from tests.test_compliance import demo_tender, seed_demo, unclear_json
from tests.test_matching import COMPANY, NOW, assessment_json, record, settings_
from tests.test_tenders_list_api import api  # noqa: F401  (fixture)

K = SectionFlagKind
EN, NE = ProposalLanguage.EN, ProposalLanguage.NE


def req(text: str, category: str, mandatory: bool = True) -> Requirement:
    return Requirement(text=text, mandatory=mandatory, category=category, source_quote=text)


def chunk(chunk_id: int, content: str, doc_type: str = "experience_certificate") -> ChunkHit:
    return ChunkHit(chunk_id=chunk_id, document_id=chunk_id * 10, filename=f"doc{chunk_id}.txt", doc_type=DocType(doc_type),
                    expires_on=None, chunk_index=0, content=content, similarity=0.8)


EXPERIENCE = chunk(7, "Completed: Gravelling of Vyas ward 3 road for Vyas Municipality, contract value Rs 1,85,40,000, "
                      "completed 2081-11-30.")


def ctx_for(rec=None, company: CompanyProfile = COMPANY, language=EN, with_bs=False) -> ProposalContext:
    return ProposalContext(record=rec or record(), company=company, language=language, now=NOW, with_bs=with_bs, tender_id=1)


def draft(body: str, cited=(7,), facts=(), missing=()) -> ProposalSectionDraft:
    return ProposalSectionDraft(body=body, cited_chunk_ids=list(cited), facts=list(facts), missing=list(missing))


def section(key: str = "relevant_experience") -> PlannedSection:
    return PlannedSection(TEMPLATES[key])


def kinds(sec: ProposalSection) -> set[SectionFlagKind]:
    return {f.kind for f in sec.flags}


# --- the section plan ------------------------------------------------------------------------------------------

def keys(rec) -> list[str]:
    return [s.key for s in plan_sections(rec)]


def test_works_template_in_order():
    assert keys(record()) == ["cover_letter", "bidder_info", "technical_compliance", "work_plan", "relevant_experience",
                              "financial_capacity", "declarations"]


def test_goods_template_has_delivery_schedule_and_non_consulting_and_unknown_use_works():
    assert keys(record(procurement_type="goods")) == ["cover_letter", "bidder_info", "technical_compliance", "delivery_plan",
                                                      "relevant_experience", "financial_capacity", "declarations"]
    assert keys(record(procurement_type="non_consulting")) == keys(record())
    assert keys(record(procurement_type="unknown")) == keys(record())


def test_consulting_rfp_template():
    assert keys(record(procurement_type="consulting", method="rfp")) == [
        "cover_letter", "understanding_tor", "methodology", "work_plan", "team", "relevant_experience"]


def test_eoi_reorders_experience_first_and_has_no_methodology():
    plan = keys(record(procurement_type="consulting", method="eoi"))
    assert plan == ["cover_letter", "relevant_experience", "team", "understanding_tor"] == list(EOI_BASE)


def test_requirements_add_and_route_sections():
    rec = record(requirements=[
        req("Valid class D or above construction licence", "eligibility"),
        req("Site engineer with 5 years of experience", "personnel"),
        req("One roller and two tippers available", "equipment"),
        req("Average turnover of Rs 1.5 crore", "financial"),
        req("One similar road contract", "experience"),
    ])
    plan = {s.key: s.requirement_indices for s in plan_sections(rec)}
    assert list(plan) == ["cover_letter", "bidder_info", "technical_compliance", "work_plan", "team", "key_equipment",
                          "relevant_experience", "financial_capacity", "declarations"]  # team + equipment added, in order
    assert plan["bidder_info"] == [0] and plan["team"] == [1] and plan["key_equipment"] == [2]
    assert plan["financial_capacity"] == [3] and plan["relevant_experience"] == [4]


def test_consulting_adds_eligibility_financial_and_declarations_when_the_notice_asks():
    rec = record(procurement_type="consulting", method="rfp",
                 requirements=[req("Firm registration and PAN", "eligibility"), req("Average turnover", "financial")],
                 required_docs=[RequiredDoc(doc_type="self_declaration", description="Self-declaration letter")])
    plan = keys(rec)
    assert plan[0] == "cover_letter" and plan[-1] == "declarations"
    assert plan.index("bidder_info") < plan.index("understanding_tor") and "financial_capacity" in plan


def test_section_query_is_topic_plus_requirements():
    rec = record(requirements=[req("One similar road contract of Rs 60 lakh", "experience")])
    [exp] = [s for s in plan_sections(rec) if s.key == "relevant_experience"]
    query = section_query(exp, rec)
    assert query.startswith(TEMPLATES["relevant_experience"].topic)
    assert "One similar road contract of Rs 60 lakh" in query and rec.scope in query  # experience adds the scope


# --- language and dates ------------------------------------------------------------------------------------------

def test_language_follows_the_notice_unless_forced():
    assert proposal_language(record(language="en")) is EN
    assert proposal_language(record(language="ne")) is NE
    assert proposal_language(record(language="mixed")) is NE
    assert proposal_language(record(language="ne"), force_english=True) is EN


def test_uses_bs_when_the_notice_wrote_a_bs_date():
    assert uses_bs(record(deadline_bs_raw="2083-08-05 B.S.")) is True
    assert uses_bs(record(), "अन्तिम मिति २०८३।०८।०५") is True
    assert uses_bs(record(), "Deadline: 21 November 2026, 12:00") is False


def test_dates_are_bs_and_ad_when_the_notice_used_bs():
    deadline = datetime(2026, 11, 21, 12, 0, tzinfo=NPT)
    assert format_date(deadline, EN, with_bs=True) == "5 Mangsir 2083 BS (21 November 2026 AD), 12:00 NPT"
    assert format_date(deadline, EN, with_bs=False) == "21 November 2026, 12:00 NPT"
    assert format_date(deadline.date(), NE, with_bs=True) == "५ मंसिर २०८३ (२०२६-११-२१)"
    ctx = ctx_for(record(deadline_ad=deadline), with_bs=True)
    assert ctx.placeholders["tender.deadline"].value == "5 Mangsir 2083 BS (21 November 2026 AD), 12:00 NPT"
    assert ctx.placeholders["today"].value == "2 Kartik 2083 BS (19 October 2026 AD)"


# --- placeholders ------------------------------------------------------------------------------------------------

def test_placeholders_resolve_from_company_and_tender():
    body = ("{{company.name}} (PAN {{company.pan}}, VAT {{company.vat}}), licence {{ company.licence_number }} class "
            "{{company.licence_class}}, bids for {{tender.title}} of {{tender.buyer}}; average turnover "
            "{{company.turnover_average}}; estimate {{tender.estimated_cost}}.")
    sec = build_section(section(), draft(body), [EXPERIENCE], ctx_for())
    assert sec.body == ("Annapurna Demo Nirman Sewa Pvt. Ltd. (PAN 999123456, VAT 999123456), licence DEMO-C-0421 class C, "
                        "bids for Gravelling of Bhanu ward 5 road of Bhanu Municipality; average turnover Rs 5,03,33,333; "
                        "estimate Rs 1,48,75,000.")
    assert sec.body_template == body and sec.flags == [] and sec.grounded
    sources = {p.name: (p.value, p.source) for p in sec.placeholders}
    assert sources["company.pan"] == ("999123456", "company") and sources["tender.buyer"] == ("Bhanu Municipality", "tender")


def test_nepali_placeholders_use_devanagari_digits():
    sec = build_section(section(), draft("{{tender.estimated_cost}}, {{tender.bid_validity_days}} दिन"), [EXPERIENCE],
                        ctx_for(record(bid_validity_days=90), language=NE))
    assert sec.body == "रु. १,४८,७५,०००, ९० दिन" and sec.title == "सम्बन्धित अनुभव"


def test_missing_value_is_marked_and_flagged_never_guessed():
    company = COMPANY.model_copy(update={"vat_number": None})
    sec = build_section(section(), draft("VAT {{company.vat}} and again {{company.vat}}."), [EXPERIENCE], ctx_for(company=company))
    assert sec.body == "VAT [MISSING: company.vat] and again [MISSING: company.vat]."
    assert [f.kind for f in sec.flags] == [K.MISSING_VALUE]  # one flag per placeholder


def test_unknown_placeholder_is_flagged():
    sec = build_section(section(), draft("Certificate {{company.iso_number}}."), [EXPERIENCE], ctx_for())
    assert sec.body == "Certificate [UNKNOWN: company.iso_number]." and kinds(sec) == {K.UNKNOWN_PLACEHOLDER}


def test_fact_from_a_chunk_is_inserted_by_code():
    fact = {"key": "vyas_value", "chunk_id": 7, "quote": "rs 1,85,40,000"}  # case-folded copy still matches
    sec = build_section(section(), draft("Vyas road, value {{fact.vyas_value}}.", cited=[], facts=[fact]), [EXPERIENCE],
                        ctx_for())
    assert sec.body == "Vyas road, value Rs 1,85,40,000."  # the KB's own text, not the model's copy
    assert sec.cited_chunk_ids == [7] and sec.grounded and sec.flags == []  # a used fact counts as a citation
    assert sec.placeholders[0].source == "chunk 7"


def test_fact_not_verbatim_or_from_an_unshown_chunk_is_flagged():
    facts = [{"key": "a", "chunk_id": 7, "quote": "Rs 2,00,00,000"}, {"key": "b", "chunk_id": 99, "quote": "Vyas"}]
    sec = build_section(section(), draft("{{fact.a}} / {{fact.b}} / {{fact.c}}", facts=facts), [EXPERIENCE], ctx_for())
    assert sec.body == "[UNVERIFIED: fact.a] / [UNVERIFIED: fact.b] / [UNKNOWN: fact.c]"
    assert kinds(sec) == {K.FACT_NOT_VERBATIM, K.UNKNOWN_PLACEHOLDER}


@pytest.mark.parametrize("figure", ["Rs 12,00,000", "रु. ३२ लाख", "45 lakh", "999123456", "DEMO-C-9999", "IFB/2083/07",
                                    "2082/83", "२०८३।०८।०५", "1,85,40,000"])
def test_invented_figures_are_masked_and_flagged(figure):
    sec = build_section(section(), draft(f"We hold {figure} as shown."), [EXPERIENCE], ctx_for())
    assert sec.body == f"We hold {UNSOURCED_MARK.format(figure)} as shown."
    assert kinds(sec) == {K.UNSOURCED_FIGURE} and figure in sec.flags[0].detail


def test_small_counts_and_placeholders_are_not_masked():
    text = "Within 90 days, 3 engineers, phase 2, ward 5; PAN {{company.pan}}."
    assert mask_unsourced(text) == (text, [])


# --- grounding --------------------------------------------------------------------------------------------------

def test_no_valid_citation_is_flagged_ungrounded():
    sec = build_section(section(), draft("Road works.", cited=[42]), [EXPERIENCE], ctx_for())
    assert not sec.grounded and sec.cited_chunk_ids == []
    assert kinds(sec) == {K.UNKNOWN_CITATION, K.UNGROUNDED}
    sec = build_section(section(), draft("Road works.", cited=[]), [EXPERIENCE], ctx_for())
    assert not sec.grounded and kinds(sec) == {K.UNGROUNDED}


def test_reported_gaps_are_flagged():
    sec = build_section(section(), draft("Road works.", missing=["completion certificate dates"]), [EXPERIENCE], ctx_for())
    assert sec.grounded and kinds(sec) == {K.GAPS_REPORTED} and "completion certificate dates" in sec.flags[0].detail


def test_no_chunks_means_no_model_call_and_a_flagged_stub(make_client):
    fake = FakeOllama([])  # any chat call would pop from an empty list
    client = make_client(fake, runs := [])
    sec = generate_section(client, section(), ctx_for(), lambda _q: [])
    assert not sec.grounded and kinds(sec) == {K.NO_KB_MATERIAL} and sec.cited_chunk_ids == []
    assert "No supporting material" in sec.body and fake.requests == [] and runs == []


def test_generate_section_one_constrained_call_at_proposal_temperature(make_client):
    reply = draft("{{company.name}} completed {{fact.vyas}}.", facts=[{"key": "vyas", "chunk_id": 7,
                                                                       "quote": "Gravelling of Vyas ward 3 road"}])
    fake = FakeOllama([reply.model_dump_json()])
    client = make_client(fake, runs := [])
    queries: list[str] = []
    sec = generate_section(client, section(), ctx_for(language=NE), lambda q: queries.append(q) or [EXPERIENCE])
    assert sec.body == "Annapurna Demo Nirman Sewa Pvt. Ltd. completed Gravelling of Vyas ward 3 road." and sec.grounded
    [call] = fake.requests
    assert call["body"]["options"]["temperature"] == 0.4 and call["body"]["format"]["title"] == "ProposalSectionDraft"
    system, user = call["body"]["messages"][0]["content"], call["body"]["messages"][1]["content"]
    assert "Write the body in Nepali (Devanagari script)" in system and "{{company.pan}}" in system
    assert "[chunk 7]" in user and "{{company.pan}} - PAN number" in user
    assert queries[0].startswith(TEMPLATES["relevant_experience"].topic)
    assert [(r.stage, r.ok) for r in runs] == [(Stage.PROPOSAL, True)]


def test_prompt_lists_only_placeholders_on_record_and_withholds_values():
    company = COMPANY.model_copy(update={"vat_number": None})
    user = build_messages(section(), ctx_for(company=company), [EXPERIENCE])[1]["content"]
    assert "{{company.pan}}" in user and "{{company.vat}}" not in user  # VAT is not on record: not offered
    assert "999123456" not in user and "1,48,75,000" not in user  # values stay with code


def test_invalid_output_twice_raises(make_client):
    client = make_client(FakeOllama(['{"body": 5}', '{"body": ""}']), runs := [])
    with pytest.raises(LLMOutputError):
        generate_section(client, section(), ctx_for(), lambda _q: [EXPERIENCE])
    assert [r.ok for r in runs] == [False] and runs[0].attempts == 2


def test_citation_rate():
    grounded = ProposalSection(key="a", title="A", body="x", grounded=True, cited_chunk_ids=[1])
    ungrounded = ProposalSection(key="b", title="B", body="x", grounded=False)
    assert citation_rate([grounded, ungrounded, grounded, grounded]) == 0.75
    assert citation_rate([]) == 0.0


# --- DB: versions, status, agent_runs, failure + resume, progress ------------------------------------------------

class DraftFake:
    """Fake Ollama: drafts cite the first chunk shown and quote its first words; other stages get fixed replies
    (Review: good scores, no gaps; the drafts never mention the bid security, so the verdict is needs_work)."""

    def __init__(self, *, invalid: bool = False, cite: bool = True) -> None:
        self.invalid, self.cite = invalid, cite
        self.drafts = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [bag_of_words_vector(t) for t in body["input"]]})
        title = body["format"]["title"]
        if title == "MatchAssessment":
            content = assessment_json(85)
        elif title == "ComplianceAssessment":
            content = unclear_json()
        elif title == "ReviewAssessment":
            content = json.dumps({"scores": {"completeness": 85, "relevance": 80, "compliance": 90}, "gaps": []})
        else:
            self.drafts += 1
            content = '{"body": 1}' if self.invalid else self._draft(body["messages"][1]["content"])
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    def _draft(self, user: str) -> str:
        [(chunk_id, text)] = re.findall(r"\[chunk (\d+)\] \([^)]*\)\n(.+)", user)[:1]
        words = " ".join(text.split()[:4])
        return json.dumps({"body": "{{company.name}}: {{fact.k}}. PAN {{company.pan}}.",
                           "cited_chunk_ids": [int(chunk_id)] if self.cite else [],
                           "facts": [{"key": "k", "chunk_id": int(chunk_id), "quote": words}], "missing": []},
                          ensure_ascii=False)


def db_client(session_factory, fake) -> LLMClient:
    return LLMClient(make_run_recorder(session_factory), settings_(), transport=httpx.MockTransport(fake.handler))


def checked_001(pg_url, make_client, db_session, session_factory):
    """Demo tender 001 through Compliance (blocked on the expired tax clearance), then overridden -> checked."""
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)
    db_session.add(Match(tender_id=tender.id, score=85, decision="pursue", reasons={}))  # as Matching leaves it
    run_compliance(db_session, db_client(session_factory, DraftFake()), tender, now=NOW)
    assert tender.status == "blocked"
    override_block(db_session, tender, overridden_by="Sita Demo Thapa", reason="FY 2082/83 clearance issued.")
    assert tender.status == "checked"
    return tender


def test_run_proposal_stores_versions_and_sets_drafted(pg_url, make_client, db_session, session_factory):
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    fake = DraftFake()
    first = run_proposal(db_session, db_client(session_factory, fake), tender, settings=settings_(), now=NOW)
    assert tender.status == "drafted" and first.version == 1 and first.language is NE  # 001 is a mixed notice
    plan = [s.key for s in first.sections]
    assert plan[0] == "cover_letter" and plan[-1] == "declarations" and fake.drafts == len(plan)
    assert first.citation_rate == 1.0 and all(s.cited_chunk_ids for s in first.sections)
    cover = first.sections[0]
    assert cover.title == "आवरण पत्र" and cover.body.startswith("Annapurna Demo Nirman Sewa Pvt. Ltd.: ")
    assert "PAN 999123456." in cover.body and cover.placeholders[1].source.startswith("chunk ")

    # agent_runs: one per section (model) + one deterministic row with the plan and the metric.
    rows = db_session.scalars(select(AgentRunRow).where(AgentRunRow.tender_id == tender.id,
                                                       AgentRunRow.stage == "proposal")).all()
    assert sum(r.model == "test-model" for r in rows) == len(plan)
    [code] = [r for r in rows if r.model == "deterministic"]
    assert code.output_json["plan"] == plan and code.output_json["citation_rate"] == 1.0

    tender.status = "checked"  # the orchestrator rewinds a drafted tender to checked for a re-draft
    db_session.commit()
    second = run_proposal(db_session, db_client(session_factory, DraftFake(cite=False)), tender, settings=settings_(),
                          now=NOW, force_english=True)
    assert second.version == 2 and second.language is EN and second.sections[0].title == "Cover letter"
    stored = db_session.scalars(select(ProposalRow).where(ProposalRow.tender_id == tender.id)
                                .order_by(ProposalRow.version)).all()
    assert [(r.version, r.language) for r in stored] == [(1, "ne"), (2, "en")]  # every version is kept
    assert stored[0].sections[0]["cited_chunk_ids"]  # sections JSON with source chunk ids
    # The facts still cite a chunk, so the second version is grounded through them.
    assert second.citation_rate == 1.0


def test_ungrounded_sections_are_stored_flagged(pg_url, make_client, db_session, session_factory):
    tender = checked_001(pg_url, make_client, db_session, session_factory)

    class NoCitation(DraftFake):
        def _draft(self, user: str) -> str:
            return json.dumps({"body": "General text.", "cited_chunk_ids": [], "facts": [], "missing": ["project list"]})

    proposal = run_proposal(db_session, db_client(session_factory, NoCitation()), tender, settings=settings_(), now=NOW)
    assert proposal.citation_rate == 0.0 and tender.status == "drafted"
    assert all(not s.grounded and {K.UNGROUNDED, K.GAPS_REPORTED} <= kinds(s) for s in proposal.sections)


def test_low_similarity_chunks_are_not_shown(pg_url, make_client, db_session, session_factory):
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    fake = DraftFake()
    proposal = run_proposal(db_session, db_client(session_factory, fake), tender, now=NOW,
                            settings=settings_(proposal_min_similarity=1.01))
    assert fake.drafts == 0 and proposal.citation_rate == 0.0
    assert all(kinds(s) == {K.NO_KB_MATERIAL} for s in proposal.sections)


def test_refused_unless_checked_and_allowed(pg_url, make_client, db_session, session_factory):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)  # matched, no compliance yet
    with pytest.raises(ValueError, match="checked"):
        run_proposal(db_session, db_client(session_factory, DraftFake()), tender, now=NOW)
    tender.status = "checked"
    db_session.commit()
    with pytest.raises(ValueError, match="analyze"):  # checked but no compliance report: the gate refuses
        run_proposal(db_session, db_client(session_factory, DraftFake()), tender, now=NOW)


def test_model_failure_fails_the_stage_then_resumes_at_proposal(pg_url, make_client, db_session, session_factory):
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    run = run_pipeline(session_factory, db_client(session_factory, DraftFake(invalid=True)), tender.id,
                       target=TenderStatus.DRAFTED, settings=settings_(), now=NOW)
    db_session.refresh(tender)
    assert run.status == "failed" and tender.status == "failed" and "proposal" in run.error
    assert db_session.scalars(select(ProposalRow)).all() == []  # no partial version
    progress = run.stages[-1]["progress"]
    assert progress["items"][0]["status"] == "failed" and progress["done"] == 0
    assert resume_status(db_session, tender) is TenderStatus.CHECKED
    assert can_draft(db_session, tender) == (True, "ok")

    run = run_pipeline(session_factory, db_client(session_factory, DraftFake()), tender.id, target=TenderStatus.DRAFTED,
                       settings=settings_(), now=NOW)
    db_session.refresh(tender)
    assert run.status == "succeeded" and run.resumed_from == "failed" and tender.status == "drafted"
    assert [s["stage"] for s in run.stages] == ["proposal"]  # Matching and Compliance are not re-run


def test_pipeline_reports_section_progress(pg_url, make_client, db_session, session_factory):
    tender = checked_001(pg_url, make_client, db_session, session_factory)
    seen: list[dict] = []
    from pipeline import orchestrator

    real = orchestrator._save_run

    def spy(factory, run_id, stages=None, **values):
        if stages and stages[-1].progress is not None:
            seen.append(stages[-1].progress.model_dump(mode="json"))
        real(factory, run_id, stages, **values)

    orchestrator._save_run = spy
    try:
        run = run_pipeline(session_factory, db_client(session_factory, DraftFake()), tender.id,
                           target=TenderStatus.DRAFTED, settings=settings_(), now=NOW)
    finally:
        orchestrator._save_run = real
    final = run.stages[-1]["progress"]
    assert run.status == "succeeded" and final["done"] == final["total"] == len(final["items"]) > 5
    assert {i["status"] for i in final["items"]} <= {"ok", "flagged"} and final["current"] is None
    dones = [p["done"] for p in seen]
    assert dones == sorted(dones) and dones[0] == 0 and seen[0]["current"] == final["items"][0]["title"]


# --- API -------------------------------------------------------------------------------------------------------

def test_proposal_api_202_progress_versions(api, db_session, pg_url, make_client, session_factory):  # noqa: F811
    from deps import get_settings
    from main import app

    app.dependency_overrides[get_settings] = lambda: settings_(review_auto_revise=False)  # one version per run here
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="extracted")
    api.holder["llm"] = LLMClient(lambda _run: None, settings_(), transport=httpx.MockTransport(DraftFake().handler))
    assert api.post(f"/tenders/{tender.id}/analyze").status_code == 202
    assert api.post(f"/tenders/{tender.id}/proposal").status_code == 409  # blocked
    assert api.post(f"/tenders/{tender.id}/compliance/override",
                    json={"overridden_by": "Sita Demo Thapa", "reason": "Clearance issued."}).status_code == 200

    resp = api.post(f"/tenders/{tender.id}/proposal")
    assert resp.status_code == 202, resp.text
    run = api.get(f"/runs/{resp.json()['id']}").json()
    assert run["status"] == "succeeded" and run["target"] == "reviewed" and run["end_status"] == "reviewed"
    stage, review = run["stages"]  # spec section 10.2: the proposal route runs Proposal and Review
    assert stage["stage"] == "proposal" and stage["progress"]["done"] == stage["progress"]["total"]
    assert review["stage"] == "review" and review["status"] == "ok"
    assert {r["stage"] for r in run["agent_runs"]} == {"proposal", "review"}

    resp = api.post(f"/tenders/{tender.id}/proposal", json={"force_english": True})  # a reviewed tender re-drafts
    assert resp.status_code == 202, resp.text
    versions = api.get(f"/tenders/{tender.id}/proposals").json()
    assert [(v["version"], v["language"]) for v in versions] == [(2, "en"), (1, "ne")]
    assert all(s["cited_chunk_ids"] for s in versions[0]["sections"])
    one = api.get(f"/proposals/{versions[1]['id']}").json()
    assert one["version"] == 1 and one["citation_rate"] == 1.0
    latest = api.get(f"/tenders/{tender.id}").json()["latest_proposal"]
    assert latest["version"] == 2 and latest["sections_total"] == latest["sections_grounded"] == len(versions[0]["sections"])

    assert api.get("/proposals/99999").status_code == 404
    assert api.get("/tenders/99999/proposals").status_code == 404
    assert api.post(f"/tenders/{tender.id}/proposal", json={"force_english": "yes please"}).status_code == 422


# --- metric script -------------------------------------------------------------------------------------------------

def test_score_proposal_arithmetic():
    from scripts.score_proposal import score

    flag = {"kind": "ungrounded", "detail": "x"}
    a = [ProposalSection(key="cover_letter", title="C", body="x", grounded=True, cited_chunk_ids=[1]),
         ProposalSection(key="declarations", title="D", body="x", grounded=False, flags=[flag])]
    b = [ProposalSection(key="cover_letter", title="C", body="x", grounded=True, cited_chunk_ids=[2])]
    m = score({"001": a, "002": b})
    assert (m["sections"], m["grounded"], m["citation_rate"]) == (3, 2, 0.667)
    assert m["by_section"] == {"cover_letter": 1.0, "declarations": 0.0}
    assert m["per_tender"] == {"001": 0.5, "002": 1.0} and m["flags"] == {"ungrounded": 1}


def test_score_proposal_offline_prints_plans(capsys):
    from scripts.score_proposal import main

    assert main([]) == 0
    out = capsys.readouterr().out
    assert "001 works/ncb ne" in out and "009 consulting/eoi en" in out and "010 consulting/rfp" in out
    assert "cover_letter, relevant_experience, team, understanding_tor" in out  # EOI order
