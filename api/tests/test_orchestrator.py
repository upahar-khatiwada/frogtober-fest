"""Pipeline orchestrator: transition table, every transition, skipped/blocked branches, failures, resume, reaper.

Real-agent runs use a schema-routed fake Ollama; state-machine tests inject runners. Needs Postgres.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models import AgentRunRow, Match, PipelineRun, Tender
from db.runs import make_run_recorder
from ingest.notices import RawNotice, upsert_notices
from pipeline import orchestrator as orch
from pipeline.llm import LLMClient
from pipeline.orchestrator import (MAIN_LINE, STEPS, TRANSITIONS, execute_run, plan_run, reap_stale_runs, resume_status,
                                   run_pipeline, start_run)
from schemas import RunStatus, Stage, StageStatus, TenderStatus
from tests.conftest import bag_of_words_vector
from tests.test_compliance import demo_tender, seed_demo, unclear_json
from tests.test_matching import NOW, add_tender, assessment_json, record, seed_company, settings_
from tests.test_scout import fixture_001, seed_text

S = TenderStatus


class SchemaFake:
    """Fake Ollama that answers by the requested schema's title (order-independent), and counts calls per schema."""

    def __init__(self, replies: dict[str, str], embed_status: int = 200) -> None:
        self.replies = replies
        self.embed_status = embed_status
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/api/embed":
            if self.embed_status != 200:
                return httpx.Response(self.embed_status, json={"error": "embed failed"})
            return httpx.Response(200, json={"embeddings": [bag_of_words_vector(t) for t in body["input"]]})
        title = body["format"]["title"]
        self.calls.append(title)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": self.replies[title]}})


GOOD = {"TenderExtraction": json.dumps(fixture_001(), ensure_ascii=False), "MatchAssessment": assessment_json(85),
        "ComplianceAssessment": unclear_json()}


def db_client(session_factory, fake) -> LLMClient:
    return LLMClient(make_run_recorder(session_factory), settings_(), transport=httpx.MockTransport(fake.handler))


def setter(to: S, calls: list | None = None, stage: Stage | None = None):
    """A runner that moves the tender to `to` and writes its agent_runs row (as every real stage does)."""

    def run(session, client, tender):
        if calls is not None:
            calls.append(stage)
        tender.status = to.value
        session.add(AgentRunRow(tender_id=tender.id, stage=(stage or Stage.SCOUT).value, model="fake", input_hash="x",
                                latency_ms=0, ok=to is not S.FAILED, attempts=1,
                                error="fake stage failed" if to is S.FAILED else None))
        session.commit()

    return run


def all_ok_runners(calls: list) -> dict:
    return {step.stage: setter(step.ok, calls, step.stage) for step in STEPS}


def run_rows(session, run_id: int) -> list[AgentRunRow]:
    return list(session.scalars(select(AgentRunRow).where(AgentRunRow.pipeline_run_id == run_id).order_by(AgentRunRow.id)))


def stage_statuses(run) -> list[tuple[str, str]]:
    return [(s["stage"], s["status"]) for s in run.stages]


# --- the transition table (pure) ------------------------------------------------------------------------------

def test_transition_table_covers_every_status_and_chains_the_steps():
    assert set(TRANSITIONS) == set(TenderStatus)
    assert [s.from_status for s in STEPS] == list(MAIN_LINE[:5]) and [s.ok for s in STEPS] == list(MAIN_LINE[1:6])
    for step in STEPS:
        assert orch.is_legal(step.from_status, step.ok) and orch.is_legal(step.from_status, S.FAILED)
        if step.branch:
            assert orch.is_legal(step.from_status, step.branch)
    assert {(STEPS[1].stage, STEPS[1].branch), (STEPS[2].stage, STEPS[2].branch)} == {
        (Stage.MATCHING, S.SKIPPED), (Stage.COMPLIANCE, S.BLOCKED)}
    for before, after in orch.HUMAN_TRANSITIONS:
        assert orch.is_legal(before, after)


@pytest.mark.parametrize("before,after", [
    (S.NEW, S.MATCHED), (S.EXTRACTED, S.CHECKED), (S.MATCHED, S.DRAFTED), (S.CHECKED, S.APPROVED),
    (S.CHECKED, S.BLOCKED), (S.SKIPPED, S.MATCHED), (S.REVIEWED, S.FAILED), (S.APPROVED, S.NEW), (S.FAILED, S.CHECKED),
    (S.NEW, S.NEW),
])
def test_illegal_transitions(before, after):
    assert not orch.is_legal(before, after)


# --- every transition with injected runners --------------------------------------------------------------------

def test_every_stage_transition_new_to_reviewed(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="new")
    calls = []
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, target=S.REVIEWED,
                       runners=all_ok_runners(calls))
    assert calls == [Stage.SCOUT, Stage.MATCHING, Stage.COMPLIANCE, Stage.PROPOSAL, Stage.REVIEW]
    assert run.status == "succeeded" and (run.start_status, run.end_status) == ("new", "reviewed")
    assert [(s["from_status"], s["to_status"], s["status"]) for s in run.stages] == [
        ("new", "extracted", "ok"), ("extracted", "matched", "ok"), ("matched", "checked", "ok"),
        ("checked", "drafted", "ok"), ("drafted", "reviewed", "ok")]
    assert all(s["duration_ms"] is not None and s["started_at"] and s["finished_at"] for s in run.stages)
    # one agent_runs row per transition, each linked to the run
    assert [r.stage for r in run_rows(db_session, run.id)] == [s.value for s in calls]
    assert run.started_at <= run.finished_at


@pytest.mark.parametrize("start,target,expected", [
    (S.NEW, S.EXTRACTED, ["scout"]),
    (S.EXTRACTED, S.MATCHED, ["matching"]),
    (S.MATCHED, S.CHECKED, ["compliance"]),
    (S.CHECKED, S.DRAFTED, ["proposal"]),
    (S.DRAFTED, S.REVIEWED, ["review"]),
])
def test_each_single_transition(session_factory, db_session, make_client, start, target, expected):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status=start.value)
    if start is S.DRAFTED:
        run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, target=target,
                           from_stage=Stage.REVIEW, runners=all_ok_runners([]))
    else:
        run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, target=target,
                           runners=all_ok_runners([]))
    assert [s["stage"] for s in run.stages] == expected and run.end_status == target.value and run.status == "succeeded"


# --- branches ---------------------------------------------------------------------------------------------------

def test_skipped_branch_stops_before_compliance(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="new")
    calls = []
    runners = all_ok_runners(calls) | {Stage.MATCHING: setter(S.SKIPPED, calls, Stage.MATCHING)}
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, runners=runners)
    assert calls == [Stage.SCOUT, Stage.MATCHING]
    assert run.status == "stopped" and run.end_status == "skipped" and run.error is None
    assert stage_statuses(run) == [("scout", "ok"), ("matching", "branched"), ("compliance", "not_run")]


def test_blocked_branch_never_reaches_proposal(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="extracted")
    calls = []
    runners = all_ok_runners(calls) | {Stage.COMPLIANCE: setter(S.BLOCKED, calls, Stage.COMPLIANCE)}
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, target=S.REVIEWED, runners=runners)
    assert calls == [Stage.MATCHING, Stage.COMPLIANCE]
    assert run.status == "stopped" and run.end_status == "blocked"
    assert stage_statuses(run)[-2:] == [("proposal", "not_run"), ("review", "not_run")]


def test_real_agents_new_to_blocked_for_demo_001(pg_url, session_factory, db_session, make_client):
    """Scout -> Matching -> Compliance on the raw 001 notice: blocked by the expired tax clearance (the demo beat)."""
    seed_demo(pg_url, make_client)
    with session_factory() as s:
        _, [tid] = upsert_notices(s, [RawNotice("seed://seed_tenders/001", seed_text("001"))])
    fake = SchemaFake(GOOD)
    run = run_pipeline(session_factory, db_client(session_factory, fake), tid, now=NOW, settings=settings_())
    assert run.status == "stopped" and run.end_status == "blocked", run.error
    assert stage_statuses(run) == [("scout", "ok"), ("matching", "ok"), ("compliance", "branched")]
    assert [(s["from_status"], s["to_status"]) for s in run.stages] == [
        ("new", "extracted"), ("extracted", "matched"), ("matched", "blocked")]
    rows = run_rows(db_session, run.id)
    assert {r.stage for r in rows} == {"scout", "matching", "compliance"}  # every transition wrote agent_runs rows
    assert all(r.tender_id == tid and r.input_hash and r.latency_ms >= 0 for r in rows)
    assert any(r.model == "deterministic" for r in rows if r.stage == "compliance")  # rules layer row
    assert db_session.get(Tender, tid).status == "blocked"


# --- failures ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("failing", [Stage.SCOUT, Stage.MATCHING, Stage.COMPLIANCE])
def test_stage_failure_marks_tender_and_run_failed(session_factory, db_session, make_client, failing):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="new")
    calls = []
    runners = all_ok_runners(calls) | {failing: setter(S.FAILED, calls, failing)}
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, runners=runners)
    assert calls[-1] is failing
    assert run.status == "failed" and run.end_status == "failed"
    assert run.error == f"{failing.value}: fake stage failed"
    statuses = dict(stage_statuses(run))
    assert statuses[failing.value] == "failed"
    assert all(v == "not_run" for k, v in statuses.items() if [s.value for s in Stage].index(k) > [s.value for s in Stage].index(failing.value))


def test_real_scout_invalid_output_twice_fails_cleanly(session_factory, db_session):
    with session_factory() as s:
        _, [tid] = upsert_notices(s, [RawNotice("seed://seed_tenders/001", seed_text("001"))])
    fake = SchemaFake({"TenderExtraction": "{}"})
    run = run_pipeline(session_factory, db_client(session_factory, fake), tid, target=S.EXTRACTED)
    assert fake.calls == ["TenderExtraction", "TenderExtraction"]  # exactly one retry
    assert run.status == "failed" and run.error.startswith("scout: attempt 2:") and "validation error" in run.error
    [row] = run_rows(db_session, run.id)
    assert (row.stage, row.ok, row.attempts) == ("scout", False, 2)


def test_crashing_stage_fails_tender_and_records_agent_run(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="matched")

    def boom(session, client, t):
        t.status = "checked"  # half-done work must be rolled back
        raise RuntimeError("disk on fire")

    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, runners={Stage.COMPLIANCE: boom})
    assert run.status == "failed" and "RuntimeError: disk on fire" in run.error
    assert stage_statuses(run) == [("compliance", "failed")]
    [row] = run_rows(db_session, run.id)
    assert (row.model, row.stage, row.ok) == ("orchestrator", "compliance", False) and "disk on fire" in row.error
    db_session.expire_all()
    assert db_session.get(Tender, tender.id).status == "failed"


def test_runner_leaving_status_unchanged_is_an_illegal_transition(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="matched")
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id,
                       runners={Stage.COMPLIANCE: lambda session, client, t: None})
    assert run.status == "failed" and "illegal transition matched -> matched" in run.error
    db_session.expire_all()
    assert db_session.get(Tender, tender.id).status == "failed"


def test_runner_jumping_ahead_is_an_illegal_transition(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="extracted")
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, target=S.MATCHED,
                       runners={Stage.MATCHING: setter(S.CHECKED, None, Stage.MATCHING)})
    assert run.status == "failed" and "illegal transition extracted -> checked" in run.error


# --- resume -----------------------------------------------------------------------------------------------------

def test_resume_status_is_derived_from_stored_data(db_session):
    seed_company(db_session, with_chunk=False)
    no_record = Tender(source_url="seed://x", raw_text="x", status="failed")
    db_session.add(no_record)
    db_session.commit()
    assert resume_status(db_session, no_record) is S.NEW
    tender = add_tender(db_session, record(), status="failed")
    assert resume_status(db_session, tender) is S.EXTRACTED  # Matching failed (it drops its row)
    db_session.add(Match(tender_id=tender.id, score=80, reasons={}, decision="pursue"))
    db_session.commit()
    assert resume_status(db_session, tender) is S.MATCHED  # Compliance failed (keeps the match)
    tender.status = "blocked"
    assert resume_status(db_session, tender) is S.BLOCKED


def test_resume_after_compliance_failure_skips_matching(pg_url, session_factory, db_session, make_client):
    seed_demo(pg_url, make_client)
    tender = demo_tender(db_session, status="extracted")
    bad = SchemaFake(GOOD | {"ComplianceAssessment": '{"status": "maybe"}'})
    first = run_pipeline(session_factory, db_client(session_factory, bad), tender.id, now=NOW, settings=settings_())
    assert first.status == "failed" and stage_statuses(first) == [("matching", "ok"), ("compliance", "failed")]
    assert first.error.startswith("compliance: attempt 2:")

    good = SchemaFake(GOOD)
    second = run_pipeline(session_factory, db_client(session_factory, good), tender.id, now=NOW, settings=settings_())
    assert (second.start_status, second.resumed_from) == ("failed", "failed")
    assert stage_statuses(second) == [("compliance", "branched")] and second.end_status == "blocked"
    assert "MatchAssessment" not in good.calls  # Matching was not re-run
    assert second.stages[0]["from_status"] == "matched"


def test_resume_after_scout_failure_restarts_at_scout(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = Tender(source_url="seed://f", raw_text="x", status="failed")
    db_session.add(tender)
    db_session.commit()
    calls = []
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, runners=all_ok_runners(calls))
    assert calls == [Stage.SCOUT, Stage.MATCHING, Stage.COMPLIANCE] and run.resumed_from == "failed"
    assert run.end_status == "checked"


# --- planning ---------------------------------------------------------------------------------------------------

def test_reanalysis_of_branches_restarts_at_matching(db_session):
    seed_company(db_session, with_chunk=False)
    for status in ("skipped", "blocked", "checked"):
        tender = add_tender(db_session, record(), status=status, url=f"seed://{status}")
        assert [s.stage for s in plan_run(db_session, tender, runners=orch.default_runners()).steps] == [
            Stage.MATCHING, Stage.COMPLIANCE]


def test_from_stage_rewinds_and_validates(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record(), status="checked")
    calls = []
    run = run_pipeline(session_factory, make_client(SchemaFake({}), []), tender.id, from_stage=Stage.SCOUT,
                       runners=all_ok_runners(calls))
    assert calls == [Stage.SCOUT, Stage.MATCHING, Stage.COMPLIANCE] and run.stages[0]["from_status"] == "new"
    new = Tender(source_url="seed://n", raw_text="x", status="new")
    db_session.add(new)
    db_session.commit()
    runners = all_ok_runners([])
    with pytest.raises(ValueError, match="has not reached"):
        plan_run(db_session, new, from_stage=Stage.MATCHING, runners=runners)
    with pytest.raises(ValueError, match="after target"):
        plan_run(db_session, tender, target=S.MATCHED, from_stage=Stage.COMPLIANCE, runners=runners)
    with pytest.raises(ValueError, match="human"):
        plan_run(db_session, tender, target=S.APPROVED, runners=runners)
    with pytest.raises(ValueError, match="not implemented"):  # a stage without a runner is refused, not skipped
        plan_run(db_session, tender, target=S.REVIEWED, runners={**orch.default_runners(), Stage.REVIEW: None})
    approved = add_tender(db_session, record(), status="approved", url="seed://a")
    with pytest.raises(ValueError, match="approved"):  # an approved bid is never re-run, even with from_stage
        plan_run(db_session, approved, from_stage=Stage.PROPOSAL, target=S.REVIEWED, runners=runners)
    with pytest.raises(ValueError, match="already extracted"):
        plan_run(db_session, add_tender(db_session, record(), url="seed://e"), target=S.EXTRACTED, runners=runners)


def test_no_company_is_refused_except_for_scout(db_session):
    new = Tender(source_url="seed://n", raw_text="x", status="new")
    db_session.add(new)
    db_session.commit()
    runners = orch.default_runners()
    assert [s.stage for s in plan_run(db_session, new, target=S.EXTRACTED, runners=runners).steps] == [Stage.SCOUT]
    with pytest.raises(ValueError, match="no company"):
        plan_run(db_session, new, runners=runners)


# --- one active run, reaper, idempotent worker ------------------------------------------------------------------

def test_one_active_run_per_tender(db_session):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record())
    run = start_run(db_session, tender, runners=all_ok_runners([]))
    assert run.status == "queued"
    with pytest.raises(ValueError, match=f"active run #{run.id}"):
        start_run(db_session, tender, runners=all_ok_runners([]))
    db_session.add(PipelineRun(tender_id=tender.id, target="checked", status="running", start_status="extracted"))
    with pytest.raises(IntegrityError):  # the partial unique index backs the check
        db_session.commit()


def test_worker_ignores_a_run_that_is_not_queued(session_factory, db_session, make_client):
    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record())
    run = start_run(db_session, tender, runners=all_ok_runners([]))
    run.status = "failed"
    db_session.commit()
    calls = []
    execute_run(session_factory, make_client(SchemaFake({}), []), run.id, runners=all_ok_runners(calls))
    assert calls == []


def test_reaper_marks_stale_runs_failed_and_leaves_fresh_ones(session_factory, db_session):
    seed_company(db_session, with_chunk=False)
    stale_t, fresh_t = (add_tender(db_session, record(), url=f"seed://{n}") for n in ("a", "b"))
    old = datetime.now(UTC) - timedelta(hours=1)
    stages = [{"stage": "matching", "status": "running", "from_status": "extracted"},
              {"stage": "compliance", "status": "pending", "from_status": "matched"}]
    stale = PipelineRun(tender_id=stale_t.id, target="checked", status="running", start_status="extracted",
                        stages=stages, heartbeat_at=old)
    fresh = PipelineRun(tender_id=fresh_t.id, target="checked", status="queued", start_status="extracted", stages=stages)
    db_session.add_all([stale, fresh])
    db_session.commit()
    assert reap_stale_runs(session_factory, max_age_s=600) == 1
    db_session.expire_all()
    assert stale.status == "failed" and "no progress" in stale.error and stale.end_status == "extracted"
    assert [s["status"] for s in stale.stages] == ["failed", "not_run"] and stale.finished_at
    assert fresh.status == "queued"
    assert reap_stale_runs(session_factory) == 1  # startup: everything active is interrupted
    db_session.expire_all()
    assert fresh.status == "failed" and "restarted" in fresh.error


def test_startup_reaps_interrupted_runs(session_factory, db_session):
    from fastapi.testclient import TestClient

    from deps import get_sessionmaker
    from main import app

    seed_company(db_session, with_chunk=False)
    tender = add_tender(db_session, record())
    run = PipelineRun(tender_id=tender.id, target="checked", status="running", start_status="extracted")
    db_session.add(run)
    db_session.commit()
    app.dependency_overrides[get_sessionmaker] = lambda: session_factory
    try:
        with TestClient(app):
            pass
    finally:
        app.dependency_overrides.clear()
    db_session.expire_all()
    assert run.status == "failed" and run.finished_at is not None
    # the tender itself was never touched: it rests at its last good state, and the next run continues from it
    assert db_session.get(Tender, tender.id).status == "extracted"


def test_stage_status_values_are_documented():
    assert {s.value for s in StageStatus} == {"pending", "running", "ok", "branched", "failed", "not_run"}
    assert {s.value for s in RunStatus} == {"queued", "running", "succeeded", "stopped", "failed"}
