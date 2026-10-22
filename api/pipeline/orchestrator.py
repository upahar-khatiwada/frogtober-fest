"""Pipeline orchestrator: the tender status state machine (spec section 10.3) and pipeline runs.

    new --Scout--> extracted --Matching--> matched --Compliance--> checked --Proposal--> drafted --Review--> reviewed --human--> approved
                                  |                      |
                                  +--> skipped           +--> blocked --human override--> checked
    any stage --LLM output invalid twice / timeout / crash--> failed --next run resumes from the last good state

Each stage function (agents.*.run_*) commits only *resting* statuses, so a tender is never left in a
transient state: a crash mid-stage rolls back to where it was. The orchestrator owns the order, checks
that every stage moved the tender along a legal edge (`TRANSITIONS`), and records each pass as a
`pipeline_runs` row (stage statuses + durations) that the UI polls through GET /runs/{id}.

Every stage writes agent_runs rows (hard rule 9): through the LLM client's recorder, through the agent
itself for code-only work (Matching pre-filters, the Compliance rules layer), or here (`model="orchestrator"`)
when a stage crashed before it could. Rows written during a run are linked to it (`db.runs.pipeline_run_context`).

Resume: a `failed` tender restarts at `resume_status`, derived from what is stored (no record -> Scout;
no match row -> Matching; a pursued match -> Compliance; stored compliance items that do not block -> Proposal;
a stored proposal version -> Review), because every failing stage drops its own partial output. Proposal reports
section-by-section progress on its stage. Review may revise the proposal once (agents.review.run_review); approval
(reviewed -> approved) is a person's, through POST /proposals/{id}/approve.
"""

import hashlib
import logging
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from agents.compliance import latest_override, load_report, override_covers, run_compliance
from agents.matching import load_company, run_matching
from agents.proposal import latest_proposal, run_proposal
from agents.review import run_review
from agents.scout import run_scout
from config import Settings, get_settings
from db.models import AgentRunRow, ComplianceItemRow, Match, PipelineRun, Tender
from db.runs import pipeline_run_context, stage_progress_context
from pipeline.llm import LLMClient
from schemas import MatchDecision, RunStatus, Stage, StageRun, StageStatus, TenderStatus

log = logging.getLogger(__name__)

S = TenderStatus

# The legal edges. Stage edges are taken by the orchestrator; HUMAN_TRANSITIONS by a person through the API.
TRANSITIONS: dict[TenderStatus, frozenset[TenderStatus]] = {
    S.NEW: frozenset({S.EXTRACTED, S.FAILED}),
    S.EXTRACTED: frozenset({S.MATCHED, S.SKIPPED, S.FAILED}),
    S.MATCHED: frozenset({S.CHECKED, S.BLOCKED, S.FAILED}),
    S.CHECKED: frozenset({S.DRAFTED, S.FAILED}),
    S.DRAFTED: frozenset({S.REVIEWED, S.FAILED}),
    S.REVIEWED: frozenset({S.APPROVED}),
    S.BLOCKED: frozenset({S.CHECKED}),
    S.SKIPPED: frozenset(),
    S.APPROVED: frozenset(),
    S.FAILED: frozenset(),
}
HUMAN_TRANSITIONS = frozenset({(S.BLOCKED, S.CHECKED), (S.REVIEWED, S.APPROVED)})  # override; approval
MAIN_LINE = (S.NEW, S.EXTRACTED, S.MATCHED, S.CHECKED, S.DRAFTED, S.REVIEWED, S.APPROVED)
ORCHESTRATOR_DONE = (S.DRAFTED, S.REVIEWED, S.APPROVED)  # human work exists; never re-run without from_stage
ORCHESTRATOR_MODEL = "orchestrator"  # agent_runs.model for a stage that crashed before it could record itself


def is_legal(before: TenderStatus, after: TenderStatus) -> bool:
    return after in TRANSITIONS[before]


@dataclass(frozen=True)
class Step:
    stage: Stage
    from_status: TenderStatus
    ok: TenderStatus
    branch: TenderStatus | None = None


STEPS: tuple[Step, ...] = (
    Step(Stage.SCOUT, S.NEW, S.EXTRACTED),
    Step(Stage.MATCHING, S.EXTRACTED, S.MATCHED, S.SKIPPED),
    Step(Stage.COMPLIANCE, S.MATCHED, S.CHECKED, S.BLOCKED),
    Step(Stage.PROPOSAL, S.CHECKED, S.DRAFTED),
    Step(Stage.REVIEW, S.DRAFTED, S.REVIEWED),
)
STEP_BY_STAGE = {step.stage: step for step in STEPS}
TARGETS = tuple(step.ok for step in STEPS)  # `approved` is human-only

Runner = Callable[[Session, LLMClient, Tender], object]


def default_runners(settings: Settings | None = None, now: datetime | None = None, *,
                    force_english: bool | None = None) -> dict[Stage, Runner | None]:
    def matching(session: Session, client: LLMClient, tender: Tender) -> object:
        result = run_matching(session, client, tender, settings=settings, now=now, rematch=True)
        if tender.status != S.MATCHED.value:  # not pursued (or failed): old compliance items are stale
            session.execute(delete(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id))
            session.commit()
        return result

    return {
        Stage.SCOUT: lambda session, client, tender: run_scout(session, client, tender),
        Stage.MATCHING: matching,
        Stage.COMPLIANCE: lambda session, client, tender: run_compliance(session, client, tender, settings=settings, now=now),
        Stage.PROPOSAL: lambda session, client, tender: run_proposal(session, client, tender, settings=settings, now=now,
                                                                    force_english=force_english),
        Stage.REVIEW: lambda session, client, tender: run_review(session, client, tender, settings=settings, now=now),
    }


# --- planning -------------------------------------------------------------------------------------------------


def resume_status(session: Session, tender: Tender) -> TenderStatus:
    """The last good state of a tender: its status, or for `failed`, what its stored data shows was completed."""
    status = TenderStatus(tender.status)
    if status is not S.FAILED:
        return status
    if tender.record_json is None:
        return S.NEW
    match = session.scalar(select(Match).where(Match.tender_id == tender.id))
    if match is None:
        return S.EXTRACTED
    if match.decision != MatchDecision.PURSUE.value:
        return S.EXTRACTED
    # A failing Compliance drops its items, so stored items mean Compliance completed (e.g. Proposal failed after).
    report = load_report(session, tender.id)
    if report is None:
        return S.MATCHED
    blocked = report.is_blocked and not override_covers(latest_override(session, tender.id), report)
    if blocked:
        return S.BLOCKED
    # A failing Proposal stores no version, so a stored version means a draft exists (e.g. Review failed after).
    return S.DRAFTED if latest_proposal(session, tender.id) is not None else S.CHECKED


def _reach(session: Session, tender: Tender) -> TenderStatus:
    """Furthest main-line status whose stage output exists (a branch counts as the step before it)."""
    status = resume_status(session, tender)
    return {S.SKIPPED: S.EXTRACTED, S.BLOCKED: S.MATCHED}.get(status, status)


@dataclass(frozen=True)
class Plan:
    steps: tuple[Step, ...]
    resumed_from: TenderStatus | None


def plan_run(session: Session, tender: Tender, *, target: TenderStatus = S.CHECKED, from_stage: Stage | None = None,
             runners: Mapping[Stage, Runner | None] | None = None) -> Plan:
    """Which steps a run will take. Raises ValueError (-> 409) when the request makes no sense."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {[t.value for t in TARGETS]} (approval is a human step)")
    current = TenderStatus(tender.status)
    if current is S.APPROVED:
        raise ValueError(f"tender {tender.id} is approved; an approved bid is not re-run")
    reach = _reach(session, tender)
    last = MAIN_LINE.index(target) - 1  # index in STEPS of the step that ends at `target`

    if from_stage is not None:
        first = STEPS.index(STEP_BY_STAGE[from_stage])
        if first > last:
            raise ValueError(f"from_stage {from_stage.value} is after target {target.value}")
        if MAIN_LINE.index(STEPS[first].from_status) > MAIN_LINE.index(reach):
            raise ValueError(f"tender {tender.id} is {current.value}; it has not reached {from_stage.value} yet")
    elif current in ORCHESTRATOR_DONE and MAIN_LINE.index(reach) >= MAIN_LINE.index(target):
        # Moving forward (drafted -> reviewed) is fine; re-running stages under existing proposal work is not.
        raise ValueError(f"tender {tender.id} is {current.value}; pass from_stage to re-run a stage")
    elif current in (S.SKIPPED, S.BLOCKED) or MAIN_LINE.index(reach) >= MAIN_LINE.index(target):
        if MAIN_LINE.index(target) <= MAIN_LINE.index(S.EXTRACTED):
            raise ValueError(f"tender {tender.id} is already {current.value}; pass from_stage=scout to re-extract")
        first = STEPS.index(STEP_BY_STAGE[Stage.MATCHING])  # re-analysis (e.g. after uploading a renewed document)
    else:
        first = MAIN_LINE.index(reach)

    steps = STEPS[first:last + 1]
    runners = runners if runners is not None else default_runners()
    if missing := [s.stage.value for s in steps if runners.get(s.stage) is None]:
        raise ValueError(f"stage(s) {missing} are not implemented yet")
    if any(s.stage is not Stage.SCOUT for s in steps) and load_company(session) is None:
        raise ValueError("no company profile; POST /company first")
    return Plan(steps, current if current is S.FAILED else None)


def active_run(session: Session, tender_id: int) -> PipelineRun | None:
    return session.scalar(select(PipelineRun).where(
        PipelineRun.tender_id == tender_id,
        PipelineRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value])))


def start_run(session: Session, tender: Tender, *, target: TenderStatus = S.CHECKED, from_stage: Stage | None = None,
              runners: Mapping[Stage, Runner | None] | None = None) -> PipelineRun:
    """Plan and store a `queued` run. One active run per tender (DB-enforced); ValueError otherwise."""
    if (busy := active_run(session, tender.id)) is not None:
        raise ValueError(f"tender {tender.id} already has an active run #{busy.id}")
    plan = plan_run(session, tender, target=target, from_stage=from_stage, runners=runners)
    run = PipelineRun(
        tender_id=tender.id, target=target.value, status=RunStatus.QUEUED.value, start_status=tender.status,
        resumed_from=plan.resumed_from.value if plan.resumed_from else None,
        stages=[StageRun(stage=s.stage, from_status=s.from_status).model_dump(mode="json") for s in plan.steps],
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError as exc:  # lost a race with another request
        session.rollback()
        raise ValueError(f"tender {tender.id} already has an active run") from exc
    return run


# --- execution ------------------------------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _save_run(factory: sessionmaker[Session], run_id: int, stages: list[StageRun] | None = None, **values: object) -> None:
    """Run bookkeeping in its own short session, so it never commits a stage's half-done tender work."""
    with factory() as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            return
        for key, value in values.items():
            setattr(run, key, value)
        if stages is not None:
            run.stages = [s.model_dump(mode="json") for s in stages]
        run.heartbeat_at = _utcnow()
        session.commit()


def _record_crash(session: Session, tender: Tender, stage: Stage, error: str, latency_ms: int) -> None:
    """A stage raised instead of returning: tender -> failed, plus the agent_runs row the stage never wrote."""
    tender.status = S.FAILED.value
    tender.updated_at = _utcnow()
    session.add(AgentRunRow(
        tender_id=tender.id, stage=stage.value, model=ORCHESTRATOR_MODEL,
        input_hash=hashlib.sha256(f"{tender.id}:{stage.value}:{error}".encode()).hexdigest(),
        output_json=None, latency_ms=latency_ms, ok=False, attempts=1, error=error,
    ))
    session.commit()


def _stage_error(session: Session, run_id: int, stage: Stage) -> str:
    row = session.scalar(select(AgentRunRow).where(
        AgentRunRow.pipeline_run_id == run_id, AgentRunRow.stage == stage.value, AgentRunRow.ok.is_(False),
    ).order_by(desc(AgentRunRow.id)))
    return row.error if row is not None and row.error else f"{stage.value} failed"


def execute_run(factory: sessionmaker[Session], client: LLMClient, run_id: int, *, settings: Settings | None = None,
                now: datetime | None = None, runners: Mapping[Stage, Runner | None] | None = None) -> None:
    """Run a queued pipeline run to its end (the FastAPI background task). Never raises; never leaves it `running`."""
    runners = {**default_runners(settings, now), **(runners or {})}
    with pipeline_run_context(run_id):
        try:
            _execute(factory, client, run_id, runners)
        except Exception as exc:  # bookkeeping itself failed (e.g. DB gone): do not leave the run `running`
            log.exception("pipeline run %s crashed", run_id)
            try:
                _save_run(factory, run_id, status=RunStatus.FAILED.value, finished_at=_utcnow(),
                          error=f"orchestrator error: {type(exc).__name__}: {exc}")
            except Exception:  # the startup / poll reaper will mark it interrupted
                log.exception("could not mark pipeline run %s failed", run_id)


def _execute(factory: sessionmaker[Session], client: LLMClient, run_id: int, runners: Mapping[Stage, Runner | None]) -> None:
    with factory() as session:
        run = session.get(PipelineRun, run_id)
        if run is None or run.status != RunStatus.QUEUED.value:
            return
        tender_id = run.tender_id
        stages = [StageRun.model_validate(s) for s in run.stages]
    _save_run(factory, run_id, status=RunStatus.RUNNING.value, started_at=_utcnow())

    outcome, error = RunStatus.SUCCEEDED, None
    with factory() as session:
        tender = session.get(Tender, tender_id)
        for stage_run in stages:
            step = STEP_BY_STAGE[stage_run.stage]
            stage_run.status, stage_run.started_at = StageStatus.RUNNING, _utcnow()
            _save_run(factory, run_id, stages)

            if tender.status != step.from_status.value:
                # Resume a failed tender / re-run an earlier stage. Not committed on its own: the stage commits it,
                # and a crash rolls it back.
                tender.status = step.from_status.value
            started = time.perf_counter()

            def on_progress(progress, stage_run=stage_run):  # Proposal: section-by-section, polled via GET /runs/{id}
                stage_run.progress = progress
                _save_run(factory, run_id, stages)

            try:
                with stage_progress_context(on_progress):
                    runners[step.stage](session, client, tender)
            except Exception as exc:
                session.rollback()
                stage_run.error = f"{type(exc).__name__}: {exc}"
                log.warning("stage %s crashed on tender %s\n%s", step.stage.value, tender_id, traceback.format_exc())
                _record_crash(session, tender, step.stage, stage_run.error, int((time.perf_counter() - started) * 1000))
            stage_run.duration_ms = int((time.perf_counter() - started) * 1000)
            stage_run.finished_at = _utcnow()

            after = TenderStatus(tender.status)
            stage_run.to_status = after
            if not is_legal(step.from_status, after):
                stage_run.error = f"illegal transition {step.from_status.value} -> {after.value}"
                _record_crash(session, tender, step.stage, stage_run.error, stage_run.duration_ms)
                after = stage_run.to_status = S.FAILED
            if after is step.ok:
                stage_run.status = StageStatus.OK
                continue
            if after is step.branch:
                stage_run.status, outcome = StageStatus.BRANCHED, RunStatus.STOPPED
            else:  # failed
                stage_run.status, outcome = StageStatus.FAILED, RunStatus.FAILED
                stage_run.error = stage_run.error or _stage_error(session, run_id, step.stage)
                error = f"{step.stage.value}: {stage_run.error}"
            break
        for rest in stages:
            if rest.status is StageStatus.PENDING:
                rest.status = StageStatus.NOT_RUN
        end_status = tender.status
    _save_run(factory, run_id, stages, status=outcome.value, end_status=end_status, finished_at=_utcnow(), error=error)


def run_pipeline(factory: sessionmaker[Session], client: LLMClient, tender_id: int, *, target: TenderStatus = S.CHECKED,
                 from_stage: Stage | None = None, settings: Settings | None = None, now: datetime | None = None,
                 runners: Mapping[Stage, Runner | None] | None = None) -> PipelineRun:
    """Start and execute a run synchronously (scripts, tests). Returns the finished run row (detached)."""
    merged = {**default_runners(settings, now), **(runners or {})}
    with factory() as session:
        tender = session.get(Tender, tender_id)
        if tender is None:
            raise ValueError(f"no tender {tender_id}")
        run_id = start_run(session, tender, target=target, from_stage=from_stage, runners=merged).id
    execute_run(factory, client, run_id, settings=settings, now=now, runners=merged)
    with factory() as session:
        run = session.get(PipelineRun, run_id)
        session.expunge(run)
        return run


# --- stuck runs -----------------------------------------------------------------------------------------------


def reap_stale_runs(factory: sessionmaker[Session], *, max_age_s: float | None = None, now: datetime | None = None) -> int:
    """Mark queued/running runs whose heartbeat is older than `max_age_s` (None: all of them) as failed.

    At startup nothing can still be running (background tasks die with the process), so every active run is
    reaped. The tender itself is already in a resting state: stages commit only resting statuses.
    """
    now = now or _utcnow()
    with factory() as session:
        query = select(PipelineRun).where(PipelineRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]))
        if max_age_s is not None:
            query = query.where(PipelineRun.heartbeat_at < now - timedelta(seconds=max_age_s))
        runs = list(session.scalars(query.with_for_update(skip_locked=True)))
        for run in runs:
            stages = [StageRun.model_validate(s) for s in run.stages]
            for stage in stages:
                if stage.status in (StageStatus.RUNNING, StageStatus.PENDING):
                    stage.status = StageStatus.FAILED if stage.status is StageStatus.RUNNING else StageStatus.NOT_RUN
                    if stage.status is StageStatus.FAILED:
                        stage.error, stage.finished_at = "interrupted", now
            run.stages = [s.model_dump(mode="json") for s in stages]
            run.status, run.finished_at = RunStatus.FAILED.value, now
            run.end_status = session.scalar(select(Tender.status).where(Tender.id == run.tender_id))
            run.error = ("interrupted: the API restarted while this run was active" if max_age_s is None
                         else f"interrupted: no progress for over {int(max_age_s)} s")
        session.commit()
        return len(runs)


def reap_from_settings(factory: sessionmaker[Session], settings: Settings | None = None) -> int:
    return reap_stale_runs(factory, max_age_s=(settings or get_settings()).pipeline_stale_after_s)
