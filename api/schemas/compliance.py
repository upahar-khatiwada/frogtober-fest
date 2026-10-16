"""Compliance stage contracts (spec section 8.1).

Items come from two places:
- the LLM, judging a requirement against KB evidence. It outputs
  `ComplianceAssessment`, whose findings have no `rule_id`, so it cannot
  claim to be a deterministic rule;
- deterministic Nepal rules in code (deadline, document expiry, ...),
  which build `ComplianceItem`s with `rule_id` set.

A `pass` with no KB chunk id is rejected unless a rule produced it
(CLAUDE.md hard rule 8).
"""

from pydantic import Field, model_validator

from schemas._base import Contract, NonEmptyStr
from schemas.enums import ComplianceStatus, Severity


class ComplianceFinding(Contract):
    requirement: NonEmptyStr
    status: ComplianceStatus
    severity: Severity
    evidence_chunk_ids: list[int] = Field(default_factory=list, description="kb_chunks.id values backing the status.")
    evidence_quote: str | None = Field(None, description="Verbatim text from the cited chunk.")
    explanation: str | None = None

    @model_validator(mode="after")
    def _pass_needs_evidence(self):
        if (
            self.status is ComplianceStatus.PASS
            and not self.evidence_chunk_ids
            and getattr(self, "rule_id", None) is None
        ):
            raise ValueError("status 'pass' requires at least one evidence_chunk_id; use 'unclear' instead")
        return self


class ComplianceAssessment(Contract):
    """LLM output for the Compliance stage."""

    items: list[ComplianceFinding]


class ComplianceItem(ComplianceFinding):
    rule_id: str | None = Field(None, description="Id of the deterministic Nepal rule that produced this item, if any.")


class ComplianceReport(Contract):
    """LLM findings plus rule-generated items. Stored per tender."""

    items: list[ComplianceItem]

    @property
    def hard_failures(self) -> list[ComplianceItem]:
        return [i for i in self.items if i.status is ComplianceStatus.FAIL and i.severity is Severity.HARD]

    @property
    def is_blocked(self) -> bool:
        """Any hard failure blocks proposal generation (spec section 10.3)."""
        return bool(self.hard_failures)
