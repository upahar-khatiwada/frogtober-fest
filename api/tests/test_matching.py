"""Matching agent: deterministic pre-filters, LLM half (fake Ollama), code-side combination, DB write, metric."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from agents.matching import (DETERMINISTIC_MODEL, POINTS, average_turnover, build_messages, combine, deterministic_signals,
                             match_extracted_tenders, run_matching, score_tender)
from config import Settings
from db.models import AgentRunRow, Company, Document, KBChunk, Match, Tender
from db.search import ChunkHit
from nepal.dates import NPT
from pipeline.llm import LLMOutputError, json_schema_for
from schemas import (CompanyProfile, DocType, MatchAssessment, MatchDecision, MatchResult, MatchSignal, SignalSource,
                     TenderRecord, TenderStatus)
from tests.conftest import FakeOllama, bag_of_words_vector

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=NPT)
COMPANY = CompanyProfile.model_validate_json((ROOT / "data" / "demo_company" / "profile.json").read_text(encoding="utf-8"))


def settings_(**over) -> Settings:
    return Settings(llm_base_url="http://ollama.test", llm_model="test-model", embed_model="test-embed", **over)


def record(**over) -> TenderRecord:
    base = dict(
        title="Gravelling of Bhanu ward 5 road", buyer="Bhanu Municipality", buyer_level="local", province="gandaki",
        district="Tanahun", scope="Road gravelling, side drains and two culverts.", procurement_type="works", method="ncb",
        language="en", deadline_ad=NOW + timedelta(days=30), estimated_cost_npr=14_875_000,
    )
    return TenderRecord.model_validate(base | over)


def assessment_json(score: int = 85, reasons=("Road gravelling and culverts are the company's core work [chunk 1]",)) -> str:
    return json.dumps({"score": score, "reasons": list(reasons)})


def sig(signals, name) -> MatchSignal:
    return next(s for s in signals if s.name == name)


# --- deterministic pre-filters ---------------------------------------------------------

def test_points_sum_to_100():
    assert sum(POINTS.values()) == 100


def test_strong_tender_gets_full_deterministic_points():
    signals = deterministic_signals(record(), COMPANY, settings=settings_(), now=NOW)
    assert all(s.source is SignalSource.DETERMINISTIC and not s.hard_skip for s in signals)
    assert sum(s.points for s in signals) == 100


@pytest.mark.parametrize("kind", ["goods", "consulting", "non_consulting"])
def test_procurement_type_outside_profile_is_hard_skip(kind):
    s = sig(deterministic_signals(record(procurement_type=kind), COMPANY, settings=settings_(), now=NOW), "procurement_type")
    assert s.hard_skip and s.points == 0 and kind in s.detail


def test_unknown_procurement_type_is_half_points_not_skip():
    s = sig(deterministic_signals(record(procurement_type="unknown"), COMPANY, now=NOW), "procurement_type")
    assert not s.hard_skip and s.points == POINTS["procurement_type"] // 2


def test_empty_profile_types_means_no_type_filter():
    company = COMPANY.model_copy(update={"procurement_types": []})
    s = sig(deterministic_signals(record(procurement_type="goods"), company, now=NOW), "procurement_type")
    assert not s.hard_skip


def test_district_not_served_is_hard_skip():
    s = sig(deterministic_signals(record(district="Jumla", province="karnali"), COMPANY, now=NOW), "geography")
    assert s.hard_skip and "Jumla" in s.detail


def test_district_match_is_case_insensitive():
    s = sig(deterministic_signals(record(district="tanahun"), COMPANY, now=NOW), "geography")
    assert not s.hard_skip and s.points == POINTS["geography"]


def test_province_only_is_partial_or_skip():
    served = sig(deterministic_signals(record(district=None, province="gandaki"), COMPANY, now=NOW), "geography")
    assert not served.hard_skip and served.points == POINTS["geography"] // 2
    other = sig(deterministic_signals(record(district=None, province="bagmati"), COMPANY, now=NOW), "geography")
    assert other.hard_skip


def test_unknown_location_is_not_a_skip():
    s = sig(deterministic_signals(record(district=None, province=None), COMPANY, now=NOW), "geography")
    assert not s.hard_skip and 0 < s.points < POINTS["geography"]


def test_average_turnover_uses_recent_years():
    assert average_turnover(COMPANY, 3) == round((42_000_000 + 51_000_000 + 58_000_000) / 3)
    assert average_turnover(COMPANY, 1) == 58_000_000
    assert average_turnover(COMPANY.model_copy(update={"turnover": []}), 3) is None


def test_budget_capacity_bands():
    avg = average_turnover(COMPANY, 3)
    within = sig(deterministic_signals(record(estimated_cost_npr=avg), COMPANY, settings=settings_(), now=NOW), "budget")
    stretch = sig(deterministic_signals(record(estimated_cost_npr=avg * 2), COMPANY, settings=settings_(), now=NOW), "budget")
    over = sig(deterministic_signals(record(estimated_cost_npr=185_000_000), COMPANY, settings=settings_(), now=NOW), "budget")
    assert (within.points, within.hard_skip) == (POINTS["budget"], False)
    assert (stretch.points, stretch.hard_skip) == (POINTS["budget"] // 2, False)
    assert over.hard_skip and over.points == 0 and "18.5 crore" in over.detail


def test_budget_cap_is_configurable():
    s = sig(deterministic_signals(record(estimated_cost_npr=185_000_000), COMPANY,
                                  settings=settings_(match_max_cost_to_turnover=4.0), now=NOW), "budget")
    assert not s.hard_skip


def test_unknown_cost_is_not_a_skip():
    s = sig(deterministic_signals(record(estimated_cost_npr=None), COMPANY, now=NOW), "budget")
    assert not s.hard_skip and 0 < s.points < POINTS["budget"]


def test_deadline_passed_in_nepal_time():
    # 12:00 NPT deadline = 06:15 UTC. At 06:14 UTC it is still open; at 06:15 UTC it has passed.
    deadline = datetime(2026, 10, 19, 12, 0, tzinfo=NPT)
    from datetime import timezone
    just_before = datetime(2026, 10, 19, 6, 14, tzinfo=timezone.utc)
    at = datetime(2026, 10, 19, 6, 15, tzinfo=timezone.utc)
    assert not sig(deterministic_signals(record(deadline_ad=deadline), COMPANY, now=just_before), "deadline").hard_skip
    assert sig(deterministic_signals(record(deadline_ad=deadline), COMPANY, now=at), "deadline").hard_skip


def test_tight_and_unknown_deadline_lose_points_but_do_not_skip():
    tight = sig(deterministic_signals(record(deadline_ad=NOW + timedelta(days=2)), COMPANY, settings=settings_(), now=NOW), "deadline")
    unknown = sig(deterministic_signals(record(deadline_ad=None), COMPANY, now=NOW), "deadline")
    for s in (tight, unknown):
        assert not s.hard_skip and s.points < POINTS["deadline"]
    assert "2 day(s) left" in tight.detail


# --- combination (code decides) ---------------------------------------------------------

def test_combine_weights_model_and_rules():
    signals = deterministic_signals(record(), COMPANY, now=NOW)  # 100
    result = combine(signals, MatchAssessment(score=50, reasons=["partly in scope"]), threshold=60, llm_weight=0.6)
    assert (result.score, result.deterministic_score, result.semantic_score) == (70, 100, 50)
    assert result.decision is MatchDecision.PURSUE


def test_reasons_say_which_signal_is_deterministic_and_which_is_model():
    result = combine(deterministic_signals(record(), COMPANY, now=NOW), MatchAssessment(score=90, reasons=["fits"]),
                     threshold=60, llm_weight=0.6)
    assert all(r.startswith(("[deterministic] ", "[model] ")) for r in result.reasons)
    assert sum(r.startswith("[deterministic]") for r in result.reasons) == 4
    assert result.reasons[-1] == "[model] fits"
    assert sig(result.signals, "semantic").source is SignalSource.MODEL


def test_hard_skip_caps_score_below_threshold_even_with_perfect_semantic():
    signals = deterministic_signals(record(estimated_cost_npr=185_000_000), COMPANY, now=NOW)
    result = combine(signals, MatchAssessment(score=100, reasons=["river training is in scope"]), threshold=60, llm_weight=0.6)
    assert result.decision is MatchDecision.SKIP and result.score == 59
    assert result.skip_reasons and "capacity" in result.skip_reasons[0]
    assert any(r.startswith("[deterministic] SKIP: ") for r in result.reasons)


def test_low_semantic_score_skips_without_hard_reason():
    result = combine(deterministic_signals(record(), COMPANY, now=NOW), MatchAssessment(score=10, reasons=["not our work"]),
                     threshold=60, llm_weight=0.6)
    assert result.score == 46 and result.decision is MatchDecision.SKIP and not result.skip_reasons
    assert result.reasons[-1] == "[deterministic] score 46 is below the threshold 60"


def test_threshold_is_inclusive_and_configurable():
    signals = deterministic_signals(record(), COMPANY, now=NOW)
    a = MatchAssessment(score=34, reasons=["x"])  # 0.6*34 + 40 = 60.4 -> 60
    assert combine(signals, a, threshold=60, llm_weight=0.6).decision is MatchDecision.PURSUE
    assert combine(signals, a, threshold=61, llm_weight=0.6).decision is MatchDecision.SKIP


def test_result_round_trips_through_json():
    result = combine(deterministic_signals(record(), COMPANY, now=NOW), MatchAssessment(score=80, reasons=["fits"]),
                     threshold=60, llm_weight=0.6, chunk_ids=[3, 4])
    assert MatchResult.model_validate(result.model_dump(mode="json")) == result


# --- LLM half -------------------------------------------------------------------------------

def chunk(cid: int = 1, text: str = "Completed 4.2 km gravel road and culverts for Vyas Municipality.") -> ChunkHit:
    return ChunkHit(chunk_id=cid, document_id=1, filename="04_experience_certificate.docx",
                    doc_type=DocType.EXPERIENCE_CERTIFICATE, expires_on=None, chunk_index=0, content=text, similarity=0.8)


def test_score_tender_asks_model_at_temperature_zero(make_client):
    fake, runs = FakeOllama([assessment_json(85)]), []
    result = score_tender(record(), COMPANY, [chunk(7)], client=make_client(fake, runs), settings=settings_(), now=NOW,
                          tender_id=3)
    body = fake.requests[0]["body"]
    assert body["options"]["temperature"] == 0.0
    assert body["format"] == json_schema_for(MatchAssessment)
    assert result.score == round(0.6 * 85 + 0.4 * 100) and result.decision is MatchDecision.PURSUE
    assert result.chunk_ids == [7]
    assert len(runs) == 1 and runs[0].stage.value == "matching" and runs[0].tender_id == 3 and runs[0].ok


def test_hard_skip_does_not_call_the_model(make_client):
    fake, runs = FakeOllama([]), []
    result = score_tender(record(procurement_type="goods"), COMPANY, [chunk()], client=make_client(fake, runs),
                          settings=settings_(), now=NOW)
    assert fake.requests == [] and runs == []
    assert result.semantic_score is None and result.decision is MatchDecision.SKIP


def test_hard_skip_can_still_ask_the_model_when_configured(make_client):
    fake, runs = FakeOllama([assessment_json(95)]), []
    result = score_tender(record(procurement_type="goods"), COMPANY, [], client=make_client(fake, runs),
                          settings=settings_(match_llm_on_hard_skip=True), now=NOW)
    assert len(fake.requests) == 1 and result.semantic_score == 95
    assert result.decision is MatchDecision.SKIP and result.score < result.threshold


def test_string_score_is_rejected_then_fails_after_one_retry(make_client):
    bad = json.dumps({"score": "85", "reasons": ["fits"]})
    fake, runs = FakeOllama([bad, bad]), []
    with pytest.raises(LLMOutputError):
        score_tender(record(), COMPANY, [], client=make_client(fake, runs), settings=settings_(), now=NOW)
    assert len(fake.requests) == 2 and len(runs) == 1 and not runs[0].ok


def test_prompt_has_scope_and_chunk_ids_but_not_code_owned_facts():
    messages = build_messages(record(), COMPANY, [chunk(42)])
    user = messages[1]["content"]
    assert "[chunk 42]" in user and "Road gravelling" in user and COMPANY.services in user
    # Deadline, cost and location are deterministic signals; the model must not weigh them.
    assert "14875000" not in user and "1.4875 crore" not in user and "Tanahun" not in user and "2026-11" not in user
    assert "Do NOT consider the deadline, budget size, location" in messages[0]["content"]


# --- DB write -------------------------------------------------------------------------------

def seed_company(session, with_chunk: bool = True) -> Company:
    from routers.company import upsert_company_profile

    company = upsert_company_profile(session, COMPANY)
    if with_chunk:
        doc = Document(company_id=company.id, filename="04_experience_certificate.docx", doc_type="experience_certificate",
                       content=b"x", sha256="0" * 64, ingest_status="ready")
        session.add(doc)
        session.flush()
        text = "Experience: gravel road, side drains and culverts for Bhanu and Vyas municipalities."
        session.add(KBChunk(document_id=doc.id, chunk_index=0, content=text, token_count=20,
                            embedding=bag_of_words_vector(text)))
        session.commit()
    return company


def add_tender(session, rec: TenderRecord, status: str = "extracted", url: str = "seed://t/1") -> Tender:
    from agents.scout import apply_record

    tender = Tender(source_url=url, raw_text="notice", status=status)
    apply_record(tender, rec)
    session.add(tender)
    session.commit()
    return tender


def test_run_matching_persists_and_sets_matched(db_session, make_client):
    seed_company(db_session)
    tender = add_tender(db_session, record())
    fake, runs = FakeOllama([assessment_json(85)], embed_fn=bag_of_words_vector), []
    result = run_matching(db_session, make_client(fake, runs), tender, settings=settings_(), now=NOW)
    assert tender.status == TenderStatus.MATCHED.value
    [row] = db_session.scalars(select(Match)).all()
    assert (row.tender_id, row.score, row.decision) == (tender.id, result.score, "pursue")
    assert MatchResult.model_validate(row.reasons) == result
    assert result.chunk_ids  # the KB chunk was retrieved and shown to the model
    assert [r.stage.value for r in runs] == ["matching"]
    assert "[chunk " in fake.requests[-1]["body"]["messages"][1]["content"]


def test_run_matching_skip_writes_code_run_row_and_no_model_call(db_session, make_client):
    seed_company(db_session)
    tender = add_tender(db_session, record(district="Jumla", province="karnali"))
    fake, runs = FakeOllama([]), []
    result = run_matching(db_session, make_client(fake, runs), tender, settings=settings_(), now=NOW)
    assert tender.status == TenderStatus.SKIPPED.value and result.decision is MatchDecision.SKIP
    assert fake.requests == [] and runs == []  # no embed, no chat
    [run] = db_session.scalars(select(AgentRunRow)).all()
    assert (run.stage, run.model, run.ok, run.tender_id) == ("matching", DETERMINISTIC_MODEL, True, tender.id)
    assert run.output_json["decision"] == "skip"


def test_rerun_replaces_match_row(db_session, make_client):
    seed_company(db_session)
    tender = add_tender(db_session, record())
    fake = FakeOllama([assessment_json(85), assessment_json(10)], embed_fn=bag_of_words_vector)
    client = make_client(fake, [])
    run_matching(db_session, client, tender, settings=settings_(), now=NOW)
    run_matching(db_session, client, tender, settings=settings_(), now=NOW)
    [row] = db_session.scalars(select(Match)).all()
    assert row.decision == "skip" and tender.status == TenderStatus.SKIPPED.value


def test_model_failure_marks_tender_failed(db_session, make_client):
    seed_company(db_session)
    tender = add_tender(db_session, record())
    fake, runs = FakeOllama(["nope", "nope"], embed_fn=bag_of_words_vector), []
    assert run_matching(db_session, make_client(fake, runs), tender, settings=settings_(), now=NOW) is None
    assert tender.status == TenderStatus.FAILED.value
    assert db_session.scalars(select(Match)).all() == []
    assert len(runs) == 1 and not runs[0].ok


def test_embedding_failure_marks_failed_and_records_run(db_session, make_client):
    seed_company(db_session)
    tender = add_tender(db_session, record())
    fake = FakeOllama([], embed_status=500)
    assert run_matching(db_session, make_client(fake, []), tender, settings=settings_(), now=NOW) is None
    assert tender.status == TenderStatus.FAILED.value
    [run] = db_session.scalars(select(AgentRunRow)).all()
    assert not run.ok and "KB retrieval failed" in run.error


@pytest.mark.parametrize("status", ["new", "checked", "drafted", "approved"])
def test_run_matching_refuses_other_statuses(db_session, make_client, status):
    seed_company(db_session)
    tender = add_tender(db_session, record(), status=status)
    with pytest.raises(ValueError):
        run_matching(db_session, make_client(FakeOllama([]), []), tender, settings=settings_(), now=NOW)


def test_run_matching_needs_a_company(db_session, make_client):
    tender = add_tender(db_session, record())
    with pytest.raises(ValueError, match="company"):
        run_matching(db_session, make_client(FakeOllama([]), []), tender, settings=settings_(), now=NOW)


def test_match_extracted_tenders_only_touches_extracted(db_session, make_client):
    seed_company(db_session, with_chunk=False)
    a = add_tender(db_session, record(procurement_type="goods"), url="seed://a")
    b = add_tender(db_session, record(procurement_type="goods"), status="new", url="seed://b")
    out = match_extracted_tenders(db_session, make_client(FakeOllama([]), []), settings=settings_(), now=NOW)
    assert list(out) == [a.id] and b.status == "new"


def test_skipped_tender_does_not_reach_compliance(db_session, make_client):
    from pipeline.orchestrator import analyze_tender

    seed_company(db_session)
    skipped = add_tender(db_session, record(procurement_type="goods"), url="seed://s")
    pursued = add_tender(db_session, record(), url="seed://p")
    calls = []
    client = make_client(FakeOllama([assessment_json(90)], embed_fn=bag_of_words_vector), [])
    for t in (skipped, pursued):
        analyze_tender(db_session, client, t, compliance=lambda s, c, tender: calls.append(tender.id),
                       settings=settings_(), now=NOW)
    assert calls == [pursued.id]
    assert (skipped.status, pursued.status) == ("skipped", "matched")


# --- metric script ----------------------------------------------------------------------------

def test_metric_script_offline(tmp_path, capsys):
    from scripts.score_matching import main

    out = tmp_path / "report.json"
    assert main(["--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    m = report["metrics"]
    assert m["relevant_precision_at_3"] == 1.0
    assert m["relevant_pursued"] == 1.0
    ranking = {r["id"]: r for r in report["ranking"]}
    for nid in ("002", "003", "008", "017", "018", "021", "032"):  # capacity, goods, passed, out of area
        assert ranking[nid]["decision"] == "skip", nid
    assert "core precision@3" in capsys.readouterr().out


def test_relevance_labels_cover_every_seed():
    from ingest.seed_tenders import load_manifest
    from config import get_settings

    labels = json.loads((ROOT / "data" / "golden" / "match_relevance.json").read_text(encoding="utf-8"))["labels"]
    manifest = load_manifest(get_settings().seed_tenders_dir)
    assert set(labels) == {n["id"] for n in manifest["notices"]}
    roles = {n["id"]: n.get("demo_role") for n in manifest["notices"]}
    assert {k for k, v in labels.items() if v["core"]} == {k for k, r in roles.items() if r in ("strong_match", "good_match")}
    assert all(v["relevant"] for v in labels.values() if v["core"])
