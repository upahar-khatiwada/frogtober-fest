"""Scout: fake-LLM extraction + deterministic post-processing, DB write, CLI table, golden set and scorer."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from agents.scout import (Grounder, build_messages, count_years, detect_language, extract_tender, format_table,
                          postprocess, run_scout, run_seed_offline, scout_new_tenders)
from nepal.dates import NPT
from pipeline.llm import LLMOutputError, json_schema_for
from schemas import DocType, Stage, TenderExtraction, TenderStatus
from scripts.score_scout import GOLDEN_PATH, manifest_golden, score
from tests.conftest import FakeOllama

ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = ROOT / "data" / "seed_tenders"
FIXTURES = Path(__file__).parent / "fixtures" / "scout"


def seed_text(nid: str) -> str:
    return next(SEED_DIR.glob(f"{nid}_*.txt")).read_text(encoding="utf-8")


def fixture_001() -> dict:
    return json.loads((FIXTURES / "001_extraction.json").read_text(encoding="utf-8"))


def g(value: str, quote: str | None = None) -> dict:
    return {"value": value, "quote": quote or value}


def minimal(**overrides) -> dict:
    """A valid TenderExtraction for notice-text tests; every field not overridden is absent/null."""
    base = {"title": g("Test work"), "buyer": g("Test Municipality"), "scope": g("Some work.", "Test work"),
            "procurement_type": "works", "method": "ncb", "buyer_level": "local"}
    return base | overrides


def post(extraction: dict, text: str):
    return postprocess(TenderExtraction.model_validate(extraction), text)


def flags_for(rec, field: str) -> list[str]:
    return [f.reason for f in rec.review_flags if f.field == field]


# --- grounding -------------------------------------------------------------------------

def test_grounder_tolerates_only_whitespace_case_digit_script():
    text = "धरौटी  रकम:\nरु. ३६,०००/- नगद"
    gr = Grounder(text)
    start, end = gr.locate("रु. 36,000/-")  # LLM wrote ASCII digits: same characters otherwise
    assert text[start:end] == "रु. ३६,०००/-"
    assert gr.locate("धरौटी रकम: रु. ३६,०००/-") is not None  # newline/double space folded
    assert gr.locate("Rs. 36,000") is None  # transliterated: not verbatim
    assert gr.locate("") is None


def test_detect_language_matches_seed_labels():
    manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    for n in manifest["notices"]:
        assert detect_language(seed_text(n["id"])).value == n["language"], n["id"]


def test_count_years():
    assert count_years("turnover of the last three fiscal years (2080/81, 2081/82 and 2082/83)") == 3
    assert count_years("pichhillo ३ आर्थिक वर्ष") == 3
    assert count_years("best three years within the last five fiscal years") is None  # never guess


# --- post-processing on a real seed notice --------------------------------------------

def test_postprocess_001_full_record():
    text = seed_text("001")
    rec = post(fixture_001(), text)
    assert rec.review_flags == [] and rec.needs_review is False
    assert rec.deadline_bs_iso == "2083-08-05"
    assert rec.deadline_ad == datetime(2026, 11, 21, 12, 0, tzinfo=NPT)
    assert rec.estimated_cost_npr == 14_875_000
    assert rec.bid_security.amount_npr == 446_000
    assert rec.bid_security.validity_days == 128  # "valid until 2083-12-15 B.S." counted from the deadline
    assert rec.bid_security_due.valid_until_bs == "2083-12-15"  # and back again: the round trip is exact
    assert rec.bid_validity_days == 90 and rec.bid_doc_fee_npr == 3000
    assert (rec.province.value, rec.district) == ("gandaki", "Tanahun")
    assert rec.language.value == "mixed"
    assert rec.criteria.min_avg_turnover_npr == 15_000_000 and rec.criteria.turnover_years is None
    assert rec.criteria.min_similar_value_npr == 6_000_000
    types = {d.doc_type for d in rec.required_docs}
    assert types == {DocType.COMPANY_REGISTRATION, DocType.BUSINESS_LICENCE, DocType.LICENCE_RENEWAL, DocType.PAN_VAT,
                     DocType.TAX_CLEARANCE, DocType.SELF_DECLARATION, DocType.JV_AGREEMENT, DocType.OTHER, DocType.BID_SECURITY}
    tax = next(d for d in rec.required_docs if d.doc_type is DocType.TAX_CLEARANCE)
    assert tax.fiscal_year_bs == "2082/83"  # "or tax return" collapsed into the clearance (Rule 40(2)(d))
    renewal = next(d for d in rec.required_docs if d.doc_type is DocType.LICENCE_RENEWAL)
    assert renewal.fiscal_year_bs == "2083/84"


def test_every_source_span_points_at_its_quote():
    text = seed_text("001")
    rec = post(fixture_001(), text)
    fields = {s.field for s in rec.sources}
    assert {"title", "deadline_ad", "deadline_bs_iso", "estimated_cost_npr", "bid_security.amount_npr", "district",
            "required_docs[0]", "requirements[0]"} <= fields
    for s in rec.sources:
        if s.quote is None and s.raw is None:
            continue
        assert s.quote_found, s.field
        start, end = s.span
        assert Grounder(text[start:end]).locate(s.quote or s.raw) is not None, s.field
    cost = next(s for s in rec.sources if s.field == "estimated_cost_npr")
    assert (cost.value, cost.raw) == (14_875_000, "Rs. 1,48,75,000/-")


# --- never guess: needs_review, raw kept, value null -----------------------------------

def test_llm_converted_amount_is_not_trusted():
    """The LLM 'helpfully' converted the amount: not verbatim, so null + flag, raw kept."""
    x = fixture_001()
    x["estimated_cost"] = g("NPR 14875000", "Estimated cost (excluding VAT): Rs. 1,48,75,000/-")
    rec = post(x, seed_text("001"))
    assert rec.estimated_cost_npr is None and rec.needs_review
    flag = next(f for f in rec.review_flags if f.field == "estimated_cost_npr")
    assert flag.raw == "NPR 14875000" and "not verbatim" in flag.reason
    src = next(s for s in rec.sources if s.field == "estimated_cost_npr")
    assert src.value is None and src.raw == "NPR 14875000" and src.quote_found  # the quote is still shown


def test_llm_converted_deadline_is_not_trusted():
    text = seed_text("012")  # "२०८३।०८।०३ गते दिनको १२:०० बजेसम्म"
    rec = post(minimal(deadline=g("2083-08-03 12:00")), text)
    assert rec.deadline_ad is None and rec.deadline_bs_iso is None and rec.deadline_bs_raw is None
    assert flags_for(rec, "deadline")
    ok = post(minimal(deadline=g("२०८३।०८।०३ गते दिनको १२:०० बजेसम्म")), text)
    assert ok.deadline_bs_iso == "2083-08-03" and ok.deadline_ad == datetime(2026, 11, 19, 12, tzinfo=NPT)
    assert ok.language.value == "ne" and not flags_for(ok, "deadline")


def test_bs_ad_disagreement_flags_and_drops_deadline():
    text = "Last date: 2083-08-05 B.S. (2026-11-22 A.D.) 12:00."
    rec = post(minimal(deadline=g("2083-08-05 B.S. (2026-11-22 A.D.) 12:00")), text)
    assert rec.deadline_ad is None and rec.deadline_bs_iso is None
    assert any("text says AD 2026-11-22" in r for r in flags_for(rec, "deadline"))


def test_corrigendum_with_old_and_new_dates_is_flagged():
    text = seed_text("007")
    raw = "२०८३/०७/१० को सट्टा २०८३/०७/२५ दिनको १२:०० बजेसम्म"
    rec = post(minimal(deadline=g(raw)), text)
    assert rec.deadline_ad is None and any("several BS dates" in r for r in flags_for(rec, "deadline"))
    good = post(minimal(deadline=g("२०८३/०७/२५ दिनको १२:०० बजेसम्म")), text)
    assert good.deadline_bs_iso == "2083-07-25" and not flags_for(good, "deadline")


def test_garbled_grouping_034_is_flagged():
    text = seed_text("034")
    rec = post(minimal(estimated_cost=g("Rs. 1,50,000,00 (Rupees Fifteen Lakh only)"),
                       deadline=g("15/08/2083 by 12 noon"), bid_security=g("Rs. 45,000")), text)
    assert rec.estimated_cost_npr is None
    assert any("invalid digit grouping" in r for r in flags_for(rec, "estimated_cost_npr"))
    assert rec.deadline_bs_iso == "2083-08-15" and rec.deadline_ad.hour == 12
    assert rec.bid_security.amount_npr == 45_000


def test_thousands_table_005_is_flagged_but_prose_amounts_parse():
    text = seed_text("005")
    rec = post(minimal(estimated_cost=g("४,८५०"), bid_security=g("१,४५,५००"), bid_doc_fee=g("रु. २,०००/-"),
                       deadline=g("२०८३/०८/१० गते दिनको १२:०० बजेसम्म")), text)
    assert rec.estimated_cost_npr is None and rec.bid_security is None
    assert any("in thousands" in r for r in flags_for(rec, "estimated_cost_npr"))
    assert rec.bid_doc_fee_npr == 2000  # has a currency marker: not a table cell
    assert rec.deadline_bs_iso == "2083-08-10"


def test_percent_bid_security_and_compound_cost_033():
    text = seed_text("033")
    rec = post(minimal(estimated_cost=g("रु. ३२ लाख ५० हजार"), bid_security=g("कबोल अङ्कको २.५ प्रतिशत")), text)
    assert rec.estimated_cost_npr == 3_250_000
    assert rec.bid_security.percent == 2.5 and rec.bid_security.amount_npr is None
    assert rec.bid_security_due.amount_npr == 81_250 and "estimated cost" in rec.bid_security_due.basis


def test_ambiguous_district_is_flagged():
    text = "Site: Nawalparasi"
    rec = post(minimal(location=g("Nawalparasi")), text)
    assert rec.district is None
    assert any("several districts" in r for r in flags_for(rec, "district"))


def test_hallucinated_text_and_docs_are_flagged_but_kept():
    text = "Construction of a culvert. Bidders must submit a firm registration certificate."
    rec = post(minimal(title=g("Construction of a bridge"),
                       required_docs=[{"name": "ISO 9001 certificate", "mandatory": True, "source_quote": "ISO 9001 certificate"}],
                       requirements=[{"text": "x", "mandatory": True, "category": "other", "source_quote": "not in notice"}]), text)
    assert rec.title == "Construction of a bridge"
    assert {f.field for f in rec.review_flags} >= {"title", "required_docs[0]", "requirements[0]"}
    assert rec.required_docs[0].doc_type is DocType.OTHER


# --- LLM call (fake Ollama) ------------------------------------------------------------

def test_extract_tender_calls_llm_once_and_records_run(make_client):
    fake = FakeOllama([json.dumps(fixture_001(), ensure_ascii=False)])
    runs: list = []
    rec = extract_tender(make_client(fake, runs), seed_text("001"), tender_id=7)
    assert rec.estimated_cost_npr == 14_875_000
    body = fake.requests[0]["body"]
    assert body["format"] == json_schema_for(TenderExtraction)
    assert body["options"]["temperature"] == 0.0 and body["options"]["num_ctx"] == 8192
    assert body["messages"][0]["content"].startswith("You extract fields")
    assert "२०८३" in body["messages"][0]["content"]  # Devanagari guidance is in the prompt
    assert len(runs) == 1 and runs[0].ok and runs[0].stage is Stage.SCOUT and runs[0].tender_id == 7
    assert runs[0].output_json["estimated_cost"]["value"] == "Rs. 1,48,75,000/-"  # the audit row keeps the raw LLM strings


def test_extract_tender_rejects_converted_types(make_client):
    """An LLM that emits an int for a raw string field fails validation (strict), retries once, then fails."""
    bad = fixture_001() | {"estimated_cost": 14875000}
    runs: list = []
    with pytest.raises(LLMOutputError):
        extract_tender(make_client(FakeOllama([json.dumps(bad)] * 2), runs), seed_text("001"))
    assert len(runs) == 1 and not runs[0].ok and runs[0].attempts == 2


def test_extract_tender_rejects_empty_text(make_client):
    with pytest.raises(ValueError):
        extract_tender(make_client(FakeOllama([]), []), "  ")


def test_build_messages_wraps_notice():
    msgs = build_messages("NOTICE")
    assert [m["role"] for m in msgs] == ["system", "user"] and "<<<\nNOTICE\n>>>" in msgs[1]["content"]


# --- CLI table -----------------------------------------------------------------------------

def test_cli_offline_table(make_client):
    fake = FakeOllama([json.dumps(fixture_001(), ensure_ascii=False), "not json", "still not json"])
    rows = run_seed_offline(make_client(fake, []), SEED_DIR, {"001", "002"})
    assert [r[0] for r in rows] == ["001", "002"] and rows[1][1] is None
    table = format_table(rows)
    assert "2083-08-05" in table and "2026-11-21 12:00" in table and "14875000" in table
    assert "002  FAILED" in table


# --- DB: tenders row + agent_runs ------------------------------------------------------------

def test_run_scout_writes_row_and_agent_run(session_factory, make_client):
    from db.models import AgentRunRow, Tender
    from db.runs import make_run_recorder
    from ingest.notices import RawNotice, upsert_notices

    with session_factory() as s:
        _, ids = upsert_notices(s, [RawNotice("seed://seed_tenders/001", seed_text("001")),
                                    RawNotice("seed://seed_tenders/002", seed_text("002"))])
    fake = FakeOllama([json.dumps(fixture_001(), ensure_ascii=False), "{}", "{}"])
    client = make_client(fake, [])
    client._record = make_run_recorder(session_factory)
    with session_factory() as s:
        results = scout_new_tenders(s, client)
    assert results[ids[0]] is not None and results[ids[1]] is None
    with session_factory() as s:
        ok, failed = (s.get(Tender, i) for i in ids)
        assert ok.status == TenderStatus.EXTRACTED.value
        assert (ok.title, ok.deadline_bs, ok.estimated_cost_npr, ok.district, ok.province, ok.procurement_type, ok.method,
                ok.language) == (fixture_001()["title"]["value"], "2083-08-05", 14_875_000, "Tanahun", "gandaki", "works", "ncb", "mixed")
        assert ok.deadline == datetime(2026, 11, 21, 12, tzinfo=NPT)
        assert ok.record_json["sources"] and ok.record_json["needs_review"] is False
        assert failed.status == TenderStatus.FAILED.value and failed.record_json is None
        rows = s.scalars(select(AgentRunRow).order_by(AgentRunRow.id)).all()
        assert [(r.tender_id, r.stage, r.ok) for r in rows] == [(ids[0], "scout", True), (ids[1], "scout", False)]
        # extracted tenders are not re-run
        assert scout_new_tenders(s, client) == {}


def test_run_scout_failed_on_empty_text(session_factory, make_client):
    from db.models import Tender

    with session_factory() as s:
        t = Tender(source_url="seed://x", raw_text="", status="new")
        s.add(t)
        s.commit()
        assert run_scout(s, make_client(FakeOllama([]), []), t) is None
        assert t.status == "failed"


# --- golden set and scorer ------------------------------------------------------------------

def test_golden_file_shape_and_labels_agree_with_manifest():
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["tenders"]
    manifest = {n["id"]: n for n in json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))["notices"]}
    assert len(golden) == 15 and len({e["id"] for e in golden}) == 15
    filled = [e for e in golden if e["status"] == "filled"]
    assert len(filled) == 5 and all(e["status"] in ("filled", "todo") for e in golden)
    for e in golden:
        assert (SEED_DIR / e["file"]).is_file() and manifest[e["id"]]["file"] == e["file"]
    for e in filled:
        m = manifest[e["id"]]["expected"]
        assert e["deadline_bs"] == m["deadline_bs"] and e["estimated_cost_npr"] == m["estimated_cost_npr"]
        assert datetime.fromisoformat(e["deadline_ad"]).tzinfo is not None
        assert all(DocType(t) for t in e["required_doc_types"])


def test_scorer_field_level_accuracy():
    golden = [
        {"id": "a", "status": "filled", "deadline_bs": "2083-08-05", "deadline_ad": "2026-11-21T12:00:00+05:45",
         "estimated_cost_npr": 100, "required_doc_types": ["pan_vat", "tax_clearance"]},
        {"id": "b", "status": "filled", "deadline_bs": None, "deadline_ad": None, "estimated_cost_npr": None,
         "required_doc_types": ["bid_security"]},
        {"id": "c", "status": "filled", "deadline_bs": "2083-01-01", "estimated_cost_npr": 5, "required_doc_types": ["other"]},
        {"id": "d", "status": "todo"},
    ]
    preds = {
        "a": {"deadline_bs_iso": "2083-08-05", "deadline_ad": "2026-11-21T12:00:59+05:45", "estimated_cost_npr": 100,
              "required_docs": [{"doc_type": "pan_vat"}, {"doc_type": "tax_clearance"}, {"doc_type": "other"}]},
        "b": {"deadline_bs_iso": "2083-08-05", "deadline_ad": None, "estimated_cost_npr": None, "required_docs": []},
        "c": None,  # Scout failed: wrong on everything
    }
    r = score(golden, preds)
    assert (r.scored, r.skipped_todo, r.failed) == (3, 1, ["c"])
    assert (r.deadline_bs.correct, r.deadline_bs.total) == (1, 3)  # b guessed a date where the label is null
    assert (r.deadline_ad.correct, r.deadline_ad.total) == (2, 2)  # same minute counts
    assert (r.budget.correct, r.budget.total) == (2, 3)
    assert (r.docs.tp, r.docs.fp, r.docs.fn) == (2, 1, 2)
    assert r.docs.exact.correct == 0 and round(r.docs.f1, 3) == round(2 * (2 / 3) * 0.5 / ((2 / 3) + 0.5), 3)


def test_scorer_on_ideal_extraction_of_001_is_perfect():
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["tenders"]
    rec = post(fixture_001(), seed_text("001"))
    r = score([e for e in golden if e["id"] == "001"], {"001": rec.model_dump(mode="json")})
    assert r.deadline_bs.accuracy == r.deadline_ad.accuracy == r.budget.accuracy == 1.0
    assert r.docs.exact.accuracy == 1.0


def test_manifest_golden_covers_all_seeds():
    manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest_golden(manifest)) == len(manifest["notices"])
