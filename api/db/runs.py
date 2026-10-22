"""`run_recorder` for `LLMClient`: one agent_runs row per stage call (hard rule 9).

While the orchestrator runs a tender it sets `current_pipeline_run`; every agent_runs row inserted in
that context (by the client's recorder or by an agent's own code-only row) is linked to the run, and
the recorder bumps the run's heartbeat so a long stage is not mistaken for a dead worker.

A stage with several items (Proposal: one per section) calls `report_progress`; inside a run the orchestrator
has set `current_stage_progress` to a callback that stores it on the run's stage (GET /runs/{id}). Outside a
run (CLI, tests) it is a no-op.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event, func, update
from sqlalchemy.orm import Session, sessionmaker

from db.models import AgentRunRow, PipelineRun
from schemas import AgentRunRecord, StageProgress

current_pipeline_run: ContextVar[int | None] = ContextVar("current_pipeline_run", default=None)
current_stage_progress: ContextVar[Callable[[StageProgress], None] | None] = ContextVar(
    "current_stage_progress", default=None)


@contextmanager
def stage_progress_context(callback: Callable[[StageProgress], None]) -> Iterator[None]:
    token = current_stage_progress.set(callback)
    try:
        yield
    finally:
        current_stage_progress.reset(token)


def report_progress(progress: StageProgress) -> None:
    """Publish a stage's item progress to the running pipeline run, if any. Never raises into the stage."""
    if (callback := current_stage_progress.get()) is not None:
        try:
            callback(progress)
        except Exception:  # progress is cosmetic; a bookkeeping hiccup must not fail the stage
            pass


@contextmanager
def pipeline_run_context(run_id: int) -> Iterator[None]:
    token = current_pipeline_run.set(run_id)
    try:
        yield
    finally:
        current_pipeline_run.reset(token)


@event.listens_for(AgentRunRow, "before_insert")
def _link_to_pipeline_run(_mapper, _connection, row: AgentRunRow) -> None:
    if row.pipeline_run_id is None:
        row.pipeline_run_id = current_pipeline_run.get()


def make_run_recorder(session_factory: sessionmaker[Session]) -> Callable[[AgentRunRecord], None]:
    """Each record is committed in its own session, so it survives a failing stage."""

    def record(run: AgentRunRecord) -> None:
        with session_factory() as session:
            session.add(AgentRunRow(**run.model_dump(mode="json")))
            if (run_id := current_pipeline_run.get()) is not None:
                session.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(heartbeat_at=func.now()))
            session.commit()

    return record
