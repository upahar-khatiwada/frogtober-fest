"""Matching stage contracts (spec section 8.1).

The LLM produces a `MatchAssessment` (score + reasons). The pursue/skip
decision is a deterministic threshold check (CLAUDE.md hard rule 5), so it
lives only on `MatchResult`, built by `MatchResult.from_assessment`.
"""

from pydantic import Field

from schemas._base import Contract, NonEmptyStr
from schemas.enums import MatchDecision


class MatchAssessment(Contract):
    score: int = Field(ge=0, le=100)
    reasons: list[NonEmptyStr] = Field(min_length=1, max_length=8)


class MatchResult(MatchAssessment):
    decision: MatchDecision
    threshold: int = Field(ge=0, le=100)

    @classmethod
    def from_assessment(cls, assessment: MatchAssessment, threshold: int) -> "MatchResult":
        decision = MatchDecision.PURSUE if assessment.score >= threshold else MatchDecision.SKIP
        return cls(**assessment.model_dump(), decision=decision, threshold=threshold)
