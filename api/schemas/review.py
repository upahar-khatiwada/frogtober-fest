"""Review stage contracts (spec section 8.1).

The LLM fills `ReviewAssessment` only: three scores and gaps, each gap tied to a tender requirement (`[R n]`) or a
proposal section. It does not choose the verdict. `agents.review` builds the stored `ReviewReport` from the model's
assessment plus deterministic checks (`ReviewCheck`: every mandatory requirement answered, no unresolved placeholders,
bid security stated when the notice asks for one, deadline not passed, sections cite the KB) and computes the
verdict in code (hard rule 5).

The verdict gates approval: `fail` cannot be approved (POST /proposals/{id}/approve -> 409), and a verdict other than
`pass` triggers at most one automatic revision pass (spec section 10.3).
"""

from pydantic import Field, model_validator

from schemas._base import Contract, NonEmptyStr
from schemas.enums import GapSource, ReviewCheckId, ReviewVerdict, Severity


class ReviewScores(Contract):
    completeness: int = Field(ge=0, le=100, description="Every tender requirement and section purpose is answered.")
    relevance: int = Field(ge=0, le=100, description="Specific to this tender's scope and buyer, not generic text.")
    compliance: int = Field(ge=0, le=100, description="Consistent with the requirements; claims nothing they contradict.")

    @property
    def lowest(self) -> int:
        return min(self.completeness, self.relevance, self.compliance)


class ReviewGapDraft(Contract):
    """One gap as the LLM reports it. `agents.review` narrows section_key / requirement_index to the real ones."""

    requirement_index: int | None = Field(None, description="n of the [R n] requirement the gap is about; null if none.")
    section_key: str | None = Field(None, description="Key of the section the gap is in; null if it is about a requirement only.")
    issue: NonEmptyStr = Field(max_length=300)
    severity: Severity = Field(description="hard: the bid would likely be judged non-responsive; soft: weaker but acceptable.")
    suggestion: str | None = Field(None, max_length=300, description="How to fix it, using only what the company has.")

    @model_validator(mode="after")
    def _tied(self):
        if self.requirement_index is None and self.section_key is None:
            raise ValueError("a gap must name a requirement_index or a section_key")
        return self


class ReviewAssessment(Contract):
    """What the LLM fills for the Review stage (temperature 0)."""

    scores: ReviewScores
    gaps: list[ReviewGapDraft] = Field(default_factory=list, max_length=12)


class ReviewCheck(Contract):
    """One deterministic check (code, hard rule 5)."""

    check: ReviewCheckId
    passed: bool
    severity: Severity = Field(description="hard: a failure makes the verdict fail; soft: needs_work.")
    detail: str


class ReviewGap(Contract):
    """A stored gap: from a deterministic check or the model. Always tied to a requirement, a section or a check."""

    source: GapSource
    check: ReviewCheckId | None = None
    requirement_index: int | None = None
    section_key: str | None = None
    issue: NonEmptyStr
    severity: Severity
    suggestion: str | None = None

    @model_validator(mode="after")
    def _tied(self):
        if self.requirement_index is None and self.section_key is None and self.check is None:
            raise ValueError("a gap must be tied to a requirement, a section or a check")
        if (self.source is GapSource.CHECK) != (self.check is not None):
            raise ValueError("check gaps name their check; model gaps do not")
        return self


class ReviewReport(Contract):
    """Stored on the reviewed proposal version (`proposals.review_json`)."""

    scores: ReviewScores = Field(description="The model's scores.")
    checks: list[ReviewCheck] = Field(default_factory=list)
    gaps: list[ReviewGap] = Field(default_factory=list)
    uncited_sections: list[str] = Field(default_factory=list, description="Section keys with no valid KB citation.")
    verdict: ReviewVerdict = Field(description="Computed by code from the checks, the gaps and the scores.")
    verdict_reasons: list[str] = Field(default_factory=list)
    pass_min_score: int = Field(70, description="REVIEW_PASS_MIN_SCORE when the verdict was computed.")
    fail_below_score: int = Field(40, description="REVIEW_FAIL_BELOW_SCORE when the verdict was computed.")
    revision_of: int | None = Field(None, description="Version this one revised automatically, if it is a revision.")
    revised_sections: list[str] = Field(default_factory=list, description="Sections redrafted from the review's gaps.")
    previous_verdict: ReviewVerdict | None = Field(None, description="Verdict of the version this one revised.")
