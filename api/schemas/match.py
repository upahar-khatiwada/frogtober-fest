"""Matching stage contracts (spec section 8.1).

The LLM produces a `MatchAssessment` (semantic relevance score + reasons).
Everything else is code: deterministic pre-filters and fit points
(`MatchSignal`, source `deterministic`), the combined score, and the
pursue/skip decision (CLAUDE.md hard rule 5). `agents.matching.combine`
builds the `MatchResult`; `from_assessment` is the plain threshold check.
"""

from pydantic import Field

from schemas._base import Contract, NonEmptyStr
from schemas.enums import MatchDecision, SignalSource


class MatchAssessment(Contract):
    score: int = Field(ge=0, le=100)
    reasons: list[NonEmptyStr] = Field(min_length=1, max_length=8)


class MatchSignal(Contract):
    """One input to the match score. `hard_skip` signals force decision `skip` whatever the other points."""

    name: NonEmptyStr = Field(description="procurement_type, geography, budget, deadline or semantic.")
    source: SignalSource
    points: int = Field(ge=0)
    max_points: int = Field(ge=0)
    hard_skip: bool = False
    detail: NonEmptyStr


class MatchResult(MatchAssessment):
    # Each reason is prefixed "[deterministic]" or "[model]" so a reader can tell code from judgement.
    reasons: list[NonEmptyStr] = Field(min_length=1, max_length=16)
    decision: MatchDecision
    threshold: int = Field(ge=0, le=100)
    deterministic_score: int | None = Field(None, ge=0, le=100, description="Sum of deterministic fit points (0-100).")
    semantic_score: int | None = Field(
        None, ge=0, le=100, description="The LLM's relevance score; null when the model was not asked (hard skip)."
    )
    llm_weight: float | None = Field(None, ge=0, le=1, description="Weight of semantic_score in score.")
    skip_reasons: list[NonEmptyStr] = Field(default_factory=list, description="Deterministic hard-skip reasons.")
    signals: list[MatchSignal] = Field(default_factory=list)
    chunk_ids: list[int] = Field(default_factory=list, description="KB chunks shown to the model.")

    @classmethod
    def from_assessment(cls, assessment: MatchAssessment, threshold: int) -> "MatchResult":
        decision = MatchDecision.PURSUE if assessment.score >= threshold else MatchDecision.SKIP
        return cls(**assessment.model_dump(), decision=decision, threshold=threshold)
