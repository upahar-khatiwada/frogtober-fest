"""Pipeline run endpoints (spec section 10.2): the Runs page and status polling.

A run is one orchestrated pass over one tender (`pipeline_runs`, written by pipeline/orchestrator.py),
started by POST /tenders/{id}/analyze. Both endpoints first reap runs whose worker stopped making
progress, so a poller never waits on a run that can no longer finish.

GET /agent-runs is the audit log itself (spec section 11 `agent_runs`, hard rule 9): every model call, code-only stage
row and human action (approvals, section edits), whether or not a pipeline run wrote it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from db.models import AgentRunRow, PipelineRun, Tender
from deps import get_session, get_sessionmaker, get_settings
from pipeline.orchestrator import reap_from_settings
from schemas import AgentRun, AgentRunView, PipelineRunDetail, PipelineRunView, RunStatus, Stage

router = APIRouter(prefix="/runs", tags=["runs"])
agent_runs_router = APIRouter(prefix="/agent-runs", tags=["runs"])


def run_view(run: PipelineRun, title: str | None) -> PipelineRunView:
    duration = None
    if run.started_at and run.finished_at:
        duration = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
    return PipelineRunView(
        id=run.id, tender_id=run.tender_id, tender_title=title, target=run.target, status=run.status,
        start_status=run.start_status, resumed_from=run.resumed_from, end_status=run.end_status, stages=run.stages,
        error=run.error, created_at=run.created_at, started_at=run.started_at, finished_at=run.finished_at,
        duration_ms=duration,
    )


def agent_run_view(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        id=row.id, tender_id=row.tender_id, stage=row.stage, model=row.model, input_hash=row.input_hash,
        output_json=row.output_json, latency_ms=row.latency_ms, ok=row.ok, attempts=row.attempts, error=row.error,
        raw_output=row.raw_output, cached=row.cached, pipeline_run_id=row.pipeline_run_id, created_at=row.created_at,
    )


@router.get("")
def list_runs(
    session: Annotated[Session, Depends(get_session)],
    factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
    settings: Annotated[Settings, Depends(get_settings)],
    tender_id: int | None = None,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PipelineRunView]:
    """Pipeline runs, newest first (the Runs page)."""
    reap_from_settings(factory, settings)
    query = select(PipelineRun, Tender.title).join(Tender, Tender.id == PipelineRun.tender_id)
    if tender_id is not None:
        query = query.where(PipelineRun.tender_id == tender_id)
    if run_status is not None:
        query = query.where(PipelineRun.status == run_status.value)
    query = query.order_by(desc(PipelineRun.id)).limit(limit).offset(offset)
    return [run_view(run, title) for run, title in session.execute(query)]


@router.get("/{run_id}", responses={status.HTTP_404_NOT_FOUND: {"description": "No such run"}})
def get_run(
    run_id: int,
    session: Annotated[Session, Depends(get_session)],
    factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PipelineRunDetail:
    """Run status for polling (the UI polls every 2 s, spec section 9.2): stages with durations, plus its agent_runs."""
    reap_from_settings(factory, settings)
    row = session.execute(select(PipelineRun, Tender.title).join(Tender, Tender.id == PipelineRun.tender_id)
                          .where(PipelineRun.id == run_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No run {run_id}")
    run, title = row
    agent_runs = session.scalars(select(AgentRunRow).where(AgentRunRow.pipeline_run_id == run_id).order_by(AgentRunRow.id))
    return PipelineRunDetail(**run_view(run, title).model_dump(), agent_runs=[agent_run_view(r) for r in agent_runs])


@agent_runs_router.get("")
def list_agent_runs(
    session: Annotated[Session, Depends(get_session)],
    tender_id: int | None = None,
    stage: Stage | None = None,
    ok: bool | None = None,
    pipeline_run_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunView]:
    """agent_runs rows, newest first, with the tender title (the Runs page audit log)."""
    query = select(AgentRunRow, Tender.title).outerjoin(Tender, Tender.id == AgentRunRow.tender_id)
    if tender_id is not None:
        query = query.where(AgentRunRow.tender_id == tender_id)
    if stage is not None:
        query = query.where(AgentRunRow.stage == stage.value)
    if ok is not None:
        query = query.where(AgentRunRow.ok.is_(ok))
    if pipeline_run_id is not None:
        query = query.where(AgentRunRow.pipeline_run_id == pipeline_run_id)
    query = query.order_by(desc(AgentRunRow.id)).limit(limit).offset(offset)
    return [AgentRunView(**agent_run_view(row).model_dump(), tender_title=title) for row, title in session.execute(query)]
