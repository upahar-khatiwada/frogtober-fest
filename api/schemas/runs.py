"""AgentRun: one audit row per LLM stage call (`agent_runs`, spec section 11).

`pipeline.llm.LLMClient` builds these and hands them to its `run_recorder`
callback (CLAUDE.md hard rule 9).
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from schemas._base import Contract
from schemas.enums import Stage


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


class AgentRun(AgentRunRecord):
    """A stored agent_runs row, as served by GET /runs/{id}."""

    id: int
    created_at: datetime
