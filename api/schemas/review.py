"""Review stage contract (spec section 8.1).

The verdict gates approval: the UI disables Approve while it is "fail"
(spec section 9.2), and "fail" triggers one optional revision (section 10.3).
"""

from pydantic import Field

from schemas._base import Contract, NonEmptyStr
from schemas.enums import ReviewVerdict, Severity


class ReviewScores(Contract):
    completeness: int = Field(ge=0, le=100)
    relevance: int = Field(ge=0, le=100)
    compliance: int = Field(ge=0, le=100)


class ReviewGap(Contract):
    section_title: str | None = Field(None, description="Proposal section the gap is in; null if proposal-wide.")
    issue: NonEmptyStr
    severity: Severity
    suggestion: str | None = None


class ReviewReport(Contract):
    scores: ReviewScores
    gaps: list[ReviewGap] = Field(default_factory=list)
    verdict: ReviewVerdict
