"""Compliance agent: rule/model routing, the demo expired-document hard fail, unclear-never-pass, override, DB, metric."""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from agents.compliance import (CHECKABLE, assess, build_messages, check_requirements, compliance_view, covering_rules,
                               ground, load_document_meta, load_report, model_item, needs_model, override_block,
                               proposal_allowed, run_compliance)
from agents.scout import Grounder
from db.models import AgentRunRow, ComplianceItemRow, ComplianceOverrideRow, Document, KBChunk, Tender
from nepal.rules import DocumentMeta
from pipeline.llm import LLMOutputError, json_schema_for
from schemas import ComplianceAssessment, ComplianceItem, Requirement, TenderRecord
from scripts.score_compliance import LABELS_PATH, demo_kb, matches, oracle_record, score
from tests.conftest import FakeOllama, bag_of_words_vector
from tests.test_matching import COMPANY, NOW, ROOT, add_tender, assessment_json

GOLDEN = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
MANIFEST = {n["id"]: n for n in json.loads((ROOT / "data" / "seed_tenders" / "manifest.json").read_text(encoding="utf-8"))["notices"]}
KB = demo_kb()


def notice_text(nid: str) -> str:
    return (ROOT / "data" / "seed_tenders" / MANIFEST[nid]["file"]).read_text(encoding="utf-8")


def golden_record(nid: str) -> TenderRecord:
    return oracle_record(MANIFEST[nid], notice_text(nid), GOLDEN["tenders"][nid])


def chunk_with(text: str):
    return next(c for c in KB.chunks if text in c.content)


def unclear_json(why: str = "The excerpts do not mention it.") -> str:
    return json.dumps({"status": "unclear", "evidence_chunk_ids": [], "evidence_quote": None, "explanation": why})


def verdict_json(status: str, chunk_id: int, quote: str, why: str = "Shown in the excerpt.") -> str:
    return json.dumps({"status": status, "evidence_chunk_ids": [chunk_id], "evidence_quote": quote, "explanation": why})


def req(text: str, category: str = "eligibility", mandatory: bool = True, quote: str | None = None) -> Requirement:
    return Requirement(text=text, mandatory=mandatory, category=category, source_quote=quote or text)


def by_rule(report, rule_id: str) -> ComplianceItem:
    return next(i for i in report.items if i.rule_id == rule_id)


def model_items(report) -> list[ComplianceItem]:
    return [i for i in report.items if i.source.value == "model"]


# --- routing: which requirements go to the model ------------------------------------------------------

ALL_RULES = {"NP-REG-DOCS", "NP-BID-FORMS", "NP-PAN-VAT", "NP-TAX-CLEARANCE", "NP-LICENCE-RENEWAL", "NP-TURNOVER",
             "NP-EXPERIENCE", "NP-BID-SECURITY", "NP-JV"}


@pytest.mark.parametrize(("text", "category", "rules", "model"), [
    ("Tax clearance certificate of F/Y 2082/83", "eligibility", ["NP-TAX-CLEARANCE"], False),
    ("आ.व. २०८२/८३ को कर चुक्ता प्रमाणपत्र", "eligibility", ["NP-TAX-CLEARANCE"], False),
    ("VAT and PAN registration certificate", "eligibility", ["NP-PAN-VAT"], False),
    ("Average annual turnover of at least Rs. 1,50,00,000", "financial", ["NP-TURNOVER"], False),
    ("At least one similar road work of Rs. 60,00,000", "experience", ["NP-EXPERIENCE"], False),
    ("Self-declaration that the bidder is not blacklisted", "eligibility", ["NP-BID-FORMS"], False),
    # Partly covered: the class is not a rule, so the model judges that part.
    ("Valid firm registration and construction licence of Class D or above, renewed for F/Y 2083/84", "eligibility",
     ["NP-REG-DOCS", "NP-LICENCE-RENEWAL"], True),
    ("Key personnel: one civil engineer and one sub-engineer", "personnel", [], True),
    ("Key equipment: one excavator, one roller", "equipment", [], True),
    ("Liquid assets and/or credit facilities of not less than NPR 3,70,00,000", "financial", [], True),
])
def test_routing(text, category, rules, model):
    r = req(text, category)
    covered = covering_rules(r, ALL_RULES)
    assert covered == rules and needs_model(r, covered) is model


def test_a_rule_that_did_not_fire_covers_nothing():
    """Licence renewal is a works-only rule: on a goods tender the requirement goes to the model."""
    r = req("Business licence renewed for F/Y 2083/84")
    assert covering_rules(r, ALL_RULES - {"NP-LICENCE-RENEWAL"}) == ["NP-REG-DOCS"]
    assert covering_rules(r, set()) == [] and needs_model(r, [])


def test_prompt_shows_chunks_and_what_code_already_checks():
    chunk = chunk_with('"C" class')
    [system, user] = build_messages(req('Construction licence of class "D" or above'), COMPANY, [chunk], ["NP-REG-DOCS"])
    assert "क = A, ख = B, ग = C, घ = D" in system["content"] and "unclear" in system["content"]
    assert f"[chunk {chunk.chunk_id}]" in user["content"] and "06_construction_licence.txt" in user["content"]
    assert "Already checked by code" in user["content"] and "NP-REG-DOCS" in user["content"]
    assert str(COMPANY.turnover[0].amount_npr) not in user["content"]  # thresholds stay with code


# --- the demo expired-document case -------------------------------------------------------------------

def test_demo_expired_tax_clearance_is_a_hard_fail_and_blocks():
    """001 asks for an FY 2082/83 clearance; the demo KB has only FY 2081/82, expired 2026-07-16."""
    report = check_requirements(golden_record("001"), COMPANY, KB.documents, client=None, now=NOW)
    tax = by_rule(report, "NP-TAX-CLEARANCE")
    assert (tax.status.value, tax.severity.value) == ("fail", "hard")
    assert "F/Y 2081/82 (expired 2026-07-16)" in tax.explanation
    tax_doc = next(d for d in KB.documents if d.filename == "03_tax_clearance_2081-82.pdf")
    assert tax.evidence_document_ids == [tax_doc.document_id]
    assert tax.action_needed.startswith("Renew tax clearance for F/Y 2082/83")
    assert report.is_blocked and report.hard_failures == [tax]
    # The other demo documents are fine: registration and the new licence copy are valid at the deadline.
    assert by_rule(report, "NP-REG-DOCS").status.value == "pass"
    assert by_rule(report, "NP-LICENCE-RENEWAL").status.value == "pass"
    assert by_rule(report, "NP-PAN-VAT").status.value == "pass"
    assert by_rule(report, "NP-DOC-VALIDITY").status.value == "pass"  # 2027-07-16 > deadline + 90 days


def test_fresh_clearance_unblocks_001():
    fresh = DocumentMeta(doc_type="tax_clearance", document_id=99, chunk_id=999, fiscal_year_bs="2082/83",
                         expiry=date(2027, 7, 16))
    report = check_requirements(golden_record("001"), COMPANY, [*KB.documents, fresh], client=None, now=NOW)
    assert by_rule(report, "NP-TAX-CLEARANCE").status.value == "pass" and not report.is_blocked


def test_002_fails_on_turnover_experience_and_jv_barred():
    report = check_requirements(golden_record("002"), COMPANY, KB.documents, client=None, now=NOW)
    assert {i.rule_id for i in report.hard_failures} == {"NP-TAX-CLEARANCE", "NP-TURNOVER", "NP-EXPERIENCE"}
    jv = by_rule(report, "NP-JV")
    assert (jv.status.value, jv.severity.value) == ("fail", "soft") and "bars joint ventures" in jv.action_needed


# --- model layer: one call per uncovered requirement, evidence checked in code ------------------------------

def test_model_layer_calls_once_per_uncovered_requirement(make_client):
    record = golden_record("001")  # licence class, key personnel, key equipment go to the model
    fake = FakeOllama([unclear_json()] * 3)
    runs: list = []
    queries: list[str] = []

    def retrieve_fn(query):
        queries.append(query)
        return KB.chunks[:4]

    report = check_requirements(record, COMPANY, KB.documents, client=make_client(fake, runs), retrieve_fn=retrieve_fn,
                                now=NOW, tender_id=7)
    chats = [r for r in fake.requests if r["path"] == "/api/chat"]
    assert len(chats) == 3 == len(runs) and len(queries) == 3
    assert all(c["body"]["format"] == json_schema_for(ComplianceAssessment) for c in chats)
    assert all(c["body"]["options"]["temperature"] == 0 for c in chats)
    assert all(r.stage.value == "compliance" and r.tender_id == 7 and r.ok for r in runs)
    keys = [i.requirement for i in model_items(report)]
    assert keys == [r.text for r in record.requirements if "class" in r.text or "Key" in r.text]
    assert all(i.status.value == "unclear" and i.action_needed for i in model_items(report))
    assert "CVs" in next(i for i in model_items(report) if "personnel" in i.requirement).action_needed


def test_model_pass_with_verbatim_quote_is_kept(make_client):
    chunk = chunk_with('"C" class')
    fake = FakeOllama([verdict_json("pass", chunk.chunk_id, 'Class: "C" class (general civil construction)')])
    r = req('Construction licence of class "D" or above')
    a = assess(make_client(fake, []), r, COMPANY, [chunk])
    item = model_item(0, r, [chunk], a, ["NP-REG-DOCS"])
    assert item.status.value == "pass" and item.evidence_chunk_ids == [chunk.chunk_id]
    assert item.evidence_document_ids == [chunk.document_id] and item.evidence_quote and item.action_needed is None
    assert "checked by NP-REG-DOCS" in item.explanation


@pytest.mark.parametrize("case", ["unknown_chunk", "quote_not_in_chunk", "no_quote"])
def test_unclear_never_pass_when_the_evidence_does_not_hold(case):
    chunk, other = chunk_with('"C" class'), chunk_with("hydraulic excavators")
    a = {
        "unknown_chunk": ComplianceAssessment(status="pass", evidence_chunk_ids=[123456], evidence_quote="Class C",
                                              explanation="x"),
        "quote_not_in_chunk": ComplianceAssessment(status="pass", evidence_chunk_ids=[other.chunk_id],
                                                   evidence_quote='Class: "C" class', explanation="x"),
        "no_quote": ComplianceAssessment(status="pass", evidence_chunk_ids=[chunk.chunk_id], explanation="x"),
    }[case]
    item = model_item(0, req("Class D or above"), [chunk, other], a)
    assert item.status.value == "unclear" and not item.evidence_chunk_ids and item.evidence_quote is None
    assert "so it is unclear" in item.explanation and item.action_needed


def test_unclear_never_pass_fail_needs_evidence_too():
    a = ComplianceAssessment(status="fail", evidence_chunk_ids=[123456], evidence_quote="x", explanation="no batching plant")
    status, ids, quote, notes = ground(a, [chunk_with("hydraulic excavators")])
    assert (status.value, ids, quote) == ("unclear", [], None) and "123456" in notes[0]


def test_unclear_never_pass_schema_rejects_pass_without_chunk(make_client):
    """A chunk-less pass is invalid output: one retry, then the stage fails. It is never stored as a pass."""
    bad = json.dumps({"status": "pass", "evidence_chunk_ids": [], "evidence_quote": None, "explanation": "seems fine"})
    runs: list = []
    with pytest.raises(LLMOutputError):
        assess(make_client(FakeOllama([bad, bad]), runs), req("Key personnel"), COMPANY, KB.chunks[:2])
    assert len(runs) == 1 and not runs[0].ok and runs[0].attempts == 2


def test_unclear_never_pass_offline_and_across_all_golden_tenders():
    for nid in GOLDEN["tenders"]:
        report = check_requirements(golden_record(nid), COMPANY, KB.documents, client=None, now=NOW)
        for item in report.items:
            if item.status.value == "pass":
                assert item.evidence_chunk_ids or (item.rule_id and (item.evidence_ref or "").startswith("tender.")), item
        assert all(i.status.value == "unclear" for i in model_items(report))


def test_model_fail_on_mandatory_is_hard_and_blocks(make_client):
    chunk = chunk_with("hydraulic excavators")
    quote = "2 hydraulic excavators (JCB-class backhoe loaders)"
    fake = FakeOllama([verdict_json("fail", chunk.chunk_id, quote, "Only 2 excavators and no batching plant.")] * 2)
    r = req("Key equipment: 3 excavators, 1 batching plant", "equipment")
    mandatory = model_item(0, r, [chunk], assess(make_client(fake, []), r, COMPANY, [chunk]))
    optional = model_item(0, r.model_copy(update={"mandatory": False}), [chunk], assess(make_client(fake, []), r, COMPANY, [chunk]))
    assert (mandatory.status.value, mandatory.severity.value) == ("fail", "hard")
    assert optional.severity.value == "soft"
    assert "05_company_profile.pdf" in mandatory.action_needed and "JV partner" in mandatory.action_needed


# --- DB: document loader, persistence, status, override -----------------------------------------------------

def seed_demo(pg_url, make_client):
    from scripts.seed_demo import DEFAULT_DATA_DIR, seed

    client = make_client(FakeOllama(embed_fn=bag_of_words_vector), [])
    assert set(seed(DEFAULT_DATA_DIR, pg_url, client).values()) == {"ready"}


def demo_tender(session, nid: str = "001", status: str = "matched") -> Tender:
    return add_tender(session, golden_record(nid), status=status, url=f"seed://seed_tenders/{MANIFEST[nid]['file']}")


def test_load_document_meta(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    docs = {d.filename: d for d in load_document_meta(db_session, 1)}
    assert len(docs) == 6
    tax = docs["03_tax_clearance_2081-82.pdf"]
    assert tax.expiry == date(2026, 7, 16) and tax.fiscal_year_bs == "2081/82" and tax.doc_type.value == "tax_clearance"
    first = db_session.scalars(select(KBChunk.id).where(KBChunk.document_id == tax.document_id).order_by(KBChunk.id)).first()
    assert tax.chunk_id == first
    db_session.get(Document, tax.document_id).ingest_status = "needs_ocr"
    db_session.commit()
    assert {d.filename: d for d in load_document_meta(db_session, 1)}["03_tax_clearance_2081-82.pdf"].chunk_id is None


def test_run_compliance_blocks_demo_001_and_persists(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)
    runs: list = []
    client = make_client(FakeOllama([unclear_json()] * 3, embed_fn=bag_of_words_vector), runs)
    report = run_compliance(db_session, client, tender, now=NOW)
    assert tender.status == "blocked" and report.is_blocked

    rows = db_session.scalars(select(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id)
                              .order_by(ComplianceItemRow.id)).all()
    assert len(rows) == len(report.items)
    tax = next(r for r in rows if r.rule_id == "NP-TAX-CLEARANCE")
    tax_doc = db_session.scalars(select(Document).where(Document.filename == "03_tax_clearance_2081-82.pdf")).one()
    assert (tax.status, tax.severity, tax.source) == ("fail", "hard", "rule")
    assert tax.evidence_document_ids == [tax_doc.id] and tax.action_needed.startswith("Renew tax clearance for F/Y 2082/83")
    assert f"documents [{tax_doc.id}]" in tax.evidence
    model_rows = [r for r in rows if r.source == "model"]
    assert len(model_rows) == 3 and all(r.rule_id is None and r.requirement_index is not None for r in model_rows)
    assert load_report(db_session, tender.id) == report  # round-trips through the columns

    code_runs = db_session.scalars(select(AgentRunRow).where(AgentRunRow.stage == "compliance")).all()
    assert [(r.model, r.ok) for r in code_runs] == [("deterministic", True)]  # the rules layer
    assert len(runs) == 3 and all(r.stage.value == "compliance" for r in runs)  # one per model call (client recorder)


def test_rerun_replaces_items_and_fresh_clearance_unblocks(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)
    client = make_client(FakeOllama([unclear_json()] * 6, embed_fn=bag_of_words_vector), [])
    first = run_compliance(db_session, client, tender, now=NOW)
    doc = Document(company_id=1, filename="07_tax_clearance_2082-83.txt", doc_type="tax_clearance", content=b"x",
                   sha256="1" * 64, ingest_status="ready", fiscal_year_bs="2082/83", expires_on=date(2027, 7, 16))
    db_session.add(doc)
    db_session.flush()
    db_session.add(KBChunk(document_id=doc.id, chunk_index=0, content="Tax clearance F/Y 2082/83", token_count=5,
                           embedding=bag_of_words_vector("Tax clearance F/Y 2082/83")))
    db_session.commit()
    second = run_compliance(db_session, client, tender, now=NOW)
    assert tender.status == "checked" and not second.is_blocked
    count = db_session.scalars(select(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id)).all()
    assert len(count) == len(second.items) == len(first.items)


def test_override_path(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)
    client = make_client(FakeOllama([unclear_json()] * 9, embed_fn=bag_of_words_vector), [])
    run_compliance(db_session, client, tender, now=NOW)
    assert proposal_allowed(db_session, tender)[0] is False

    row = override_block(db_session, tender, overridden_by="Ram Demo Gurung", reason="Renewal applied for at IRO.")
    assert tender.status == "checked"
    stored = db_session.scalars(select(ComplianceOverrideRow)).one()
    assert (stored.overridden_by, stored.reason) == ("Ram Demo Gurung", "Renewal applied for at IRO.")
    assert stored.created_at is not None and stored.hard_failures == ["NP-TAX-CLEARANCE:Tax clearance for F/Y 2082/83"]
    view = compliance_view(db_session, tender.id)
    assert view.blocked and view.override.active and view.proposal_allowed and row.id == view.override.id
    assert proposal_allowed(db_session, tender) == (True, "ok")
    assert any(i.status.value == "fail" for i in view.items)  # the failure stays on the report

    # Re-check with the same failures: the override still covers them.
    run_compliance(db_session, client, tender, now=NOW)
    assert tender.status == "checked" and compliance_view(db_session, tender.id).override.active

    # A new hard failure (PAN removed from the profile) is not covered: blocked again.
    from db.models import Company
    company = db_session.get(Company, 1)
    company.profile_json = {**company.profile_json, "pan_number": None}
    db_session.commit()
    run_compliance(db_session, client, tender, now=NOW)
    view = compliance_view(db_session, tender.id)
    assert tender.status == "blocked" and not view.override.active and not view.proposal_allowed


def test_override_refused_unless_blocked(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="checked")
    with pytest.raises(ValueError, match="only a blocked tender"):
        override_block(db_session, tender, overridden_by="x", reason="y")


def test_model_failure_marks_failed(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)
    bad = json.dumps({"status": "maybe", "explanation": "x"})
    runs: list = []
    assert run_compliance(db_session, make_client(FakeOllama([bad, bad], embed_fn=bag_of_words_vector), runs), tender,
                          now=NOW) is None
    assert tender.status == "failed" and not runs[0].ok
    assert not db_session.scalars(select(ComplianceItemRow)).all()


def test_embedding_failure_marks_failed_and_records_run(pg_url, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session)
    assert run_compliance(db_session, make_client(FakeOllama([], embed_status=500), []), tender, now=NOW) is None
    assert tender.status == "failed"
    [row] = db_session.scalars(select(AgentRunRow).where(AgentRunRow.stage == "compliance")).all()
    assert not row.ok and "KB retrieval failed" in row.error


@pytest.mark.parametrize("status", ["new", "extracted", "skipped", "drafted"])
def test_run_compliance_refuses_other_statuses(db_session, make_client, status):
    assert status not in {s.value for s in CHECKABLE}
    tender = demo_tender(db_session, status=status)
    with pytest.raises(ValueError):
        run_compliance(db_session, make_client(FakeOllama([]), []), tender, now=NOW)


def test_analyze_runs_matching_then_compliance(pg_url, db_session, make_client):
    from pipeline.orchestrator import analyze_tender

    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="extracted")
    replies = ([assessment_json(85)] + [unclear_json()] * 3) * 2  # Matching, then 3 Compliance model calls; twice
    client = make_client(FakeOllama(replies, embed_fn=bag_of_words_vector), [])
    analyze_tender(db_session, client, tender, now=NOW)
    assert tender.status == "blocked"
    analyze_tender(db_session, client, tender, now=NOW)  # re-analysis from blocked is allowed
    assert tender.status == "blocked"


def test_analyze_drops_stale_items_when_no_longer_pursued(pg_url, db_session, make_client):
    from pipeline.orchestrator import analyze_tender

    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="extracted")
    client = make_client(FakeOllama([assessment_json(85)] + [unclear_json()] * 3, embed_fn=bag_of_words_vector), [])
    analyze_tender(db_session, client, tender, now=NOW)
    assert load_report(db_session, tender.id) is not None
    analyze_tender(db_session, client, tender, now=NOW + timedelta(days=60))  # deadline passed -> hard skip
    assert tender.status == "skipped" and load_report(db_session, tender.id) is None


# --- golden file + metric --------------------------------------------------------------------------------------

def test_golden_labels_are_verbatim_and_well_formed():
    for nid, labelled in GOLDEN["tenders"].items():
        grounder = Grounder(notice_text(nid))
        keys = [r["key"] for r in labelled["requirements"]]
        assert len(keys) == len(set(keys)), nid
        for r in labelled["requirements"]:
            assert grounder.locate(r["quote"]), (nid, r["key"])
            assert r["expected"] in {"pass", "fail", "unclear"} and (r.get("rule_id") or r.get("keywords")), (nid, r["key"])
            assert r["expected"] != "fail" or r["hard"]
        golden_record(nid)  # the oracle record validates


def test_golden_tax_fy_agrees_with_seed_manifest():
    for nid, labelled in GOLDEN["tenders"].items():
        fys = {d.get("fiscal_year_bs") for d in labelled["record"]["required_docs"] if d["doc_type"] == "tax_clearance"}
        assert fys == {"2082/83"}, nid
        if fy := MANIFEST[nid]["expected"].get("tax_clearance_fy"):
            assert fy == "2082/83"


def test_metric_scorer_arithmetic():
    labels = {"tenders": {"T": {"expected_blocked": True, "requirements": [
        {"key": "tax", "expected": "fail", "hard": True, "rule_id": "NP-TAX-CLEARANCE"},
        {"key": "class", "expected": "fail", "hard": True, "keywords": ["class"]},
        {"key": "pan", "expected": "pass", "hard": True, "rule_id": "NP-PAN-VAT"},
    ]}}}
    from schemas import ComplianceReport
    items = [
        ComplianceItem(requirement="Tax clearance for F/Y 2082/83", status="fail", severity="hard", source="rule",
                       rule_id="NP-TAX-CLEARANCE"),
        ComplianceItem(requirement="Licence class A only", status="unclear", severity="hard", source="model"),
        ComplianceItem(requirement="Registration documents", status="fail", severity="hard", source="rule", rule_id="NP-REG-DOCS"),
    ]
    m = score(labels, {"T": ComplianceReport(items=items)})
    assert (m["recall"], m["hard_fail_recall"], m["status_accuracy"]) == (round(2 / 3, 3), 0.5, round(1 / 3, 3))
    assert m["missed_hard_fails"] == ["T:class"] and m["uncovered"] == ["T:pan"]
    assert [f["item"] for f in m["false_hard_fails"]] == ["NP-REG-DOCS: Registration documents"]
    assert m["blocked_accuracy"] == 1.0
    assert score(labels, {"T": None})["recall"] == 0.0  # a failed stage covers nothing
    assert matches({"keywords": ["class"]}, items[1]) and not matches({"keywords": ["class"]}, items[0])


def test_offline_metric_floor():
    """Rules only, oracle records (PROGRESS.md records these numbers). The model layer can only add hard fails."""
    reports = {nid: check_requirements(golden_record(nid), COMPANY, KB.documents, client=None, now=NOW)
               for nid in GOLDEN["tenders"]}
    m = score(GOLDEN, reports)
    assert m["recall"] == 1.0 and m["blocked_accuracy"] == 1.0 and not m["false_hard_fails"]
    assert m["hard_fail_recall"] == round(9 / 11, 3)
    assert sorted(m["missed_hard_fails"]) == ["002:key_equipment", "002:licence_class"]  # model-layer requirements


def test_metric_cli_runs_offline(capsys):
    from scripts.score_compliance import main

    assert main([]) == 0
    out = capsys.readouterr().out
    assert "hard-fail recall (worst error)     0.818" in out and "rules only" in out
