"""Run records: one audit row per stage call (`agent_runs`, spec section 11), and pipeline runs.

`pipeline.llm.LLMClient` builds `AgentRunRecord`s and hands them to its
`run_recorder` callback (CLAUDE.md hard rule 9). `pipeline.orchestrator`
writes `pipeline_runs` rows: one orchestrated pass over one tender, polled
by the UI through GET /runs/{id} (spec section 10.2).
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from schemas._base import Contract
from schemas.enums import RunStatus, SectionProgress, Stage, StageStatus, TenderStatus


class AgentRunRecord(Contract):
    tender_id: int | None = None
    stage: Stage
    model: str
    input_hash: str = Field(description="sha256 of the canonical request (model, messages, schema, temperature).")
    output_json: dict[str, Any] | None = Field(None, description="Validated output; null when ok is false.")
    latency_ms: int = Field(ge=0)
    ok: bool
    attempts: int = Field(ge=1, le=2)
    error: str | None = None
    raw_output: str | None = Field(None, description="Last raw model output, kept on failure for debugging.")
    cached: bool = Field(False, description="Replayed from the LLM replay cache (LLM_REPLAY_CACHE), not a live model call.")


class AgentRun(AgentRunRecord):
    """A stored agent_runs row."""

    id: int
    pipeline_run_id: int | None = None
    created_at: datetime


class AgentRunView(AgentRun):
    """GET /agent-runs: one audit row with its tender's title (the Runs page)."""

    tender_title: str | None = None


class ProgressItem(Contract):
    key: str
    title: str
    status: SectionProgress = SectionProgress.PENDING


class StageProgress(Contract):
    """Item-by-item progress inside a running stage (Proposal: one item per section)."""

    done: int = Field(ge=0)
    total: int = Field(ge=0)
    current: str | None = Field(None, description="Title of the item being worked on.")
    items: list[ProgressItem] = Field(default_factory=list)


class StageRun(Contract):
    """One stage of a pipeline run, as stored in `pipeline_runs.stages`."""

    stage: Stage
    status: StageStatus = StageStatus.PENDING
    from_status: TenderStatus
    to_status: TenderStatus | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(None, ge=0)
    error: str | None = None
    progress: StageProgress | None = None


class AnalyzeRequest(Contract):
    """POST /tenders/{id}/analyze body (optional)."""

    target: TenderStatus = Field(TenderStatus.CHECKED, description="Stop once the tender reaches this status.")
    from_stage: Stage | None = Field(
        None, description="Re-run from this stage even if the tender is past it (e.g. `scout` re-extracts). "
                          "Default: continue from the tender's last good state.")


class PipelineRunView(Contract):
    """A pipeline run for the Runs page and polling."""

    id: int
    tender_id: int
    tender_title: str | None = None
    target: TenderStatus
    status: RunStatus
    start_status: TenderStatus
    resumed_from: TenderStatus | None = Field(None, description="Set when the run restarted a failed tender from its last good state.")
    end_status: TenderStatus | None = None
    stages: list[StageRun]
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(None, ge=0)


class PipelineRunDetail(PipelineRunView):
    """GET /runs/{id}: the run plus every agent_runs row it wrote."""

    agent_runs: list[AgentRun]
