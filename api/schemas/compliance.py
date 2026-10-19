"""Compliance stage contracts (spec section 8.1).

Items come from two layers (`agents.compliance.check_requirements`):
- **rules** (code): the deterministic Nepal rules in `nepal/rules.yaml`. They
  build `ComplianceItem`s with `rule_id` set and cite document records
  and/or KB chunks;
- **model** (LLM): one `ComplianceAssessment` per extracted requirement that
  no rule covers, judged against retrieved KB chunks. It has no `rule_id`,
  `severity` or `requirement` field, so the model can neither pose as a rule
  nor choose how much a failure matters. Code sets severity (mandatory
  -> hard) and checks the cited chunk ids and quote before keeping a pass
  or fail.

Evidence rule (CLAUDE.md hard rule 8, spec section 17): a `pass` must cite a
KB chunk id or a document record. A rule may instead cite the tender notice
itself (e.g. the deadline). Anything else is `unclear`, never `pass`.
"""

from datetime import datetime

from pydantic import Field, computed_field, model_validator

from schemas._base import Contract, NonEmptyStr
from schemas.enums import ComplianceStatus, ItemSource, Severity


class ComplianceAssessment(Contract):
    """LLM output for the Compliance stage: ONE requirement judged against the KB excerpts it was shown."""

    status: ComplianceStatus
    evidence_chunk_ids: list[int] = Field(
        default_factory=list, max_length=3, description="Ids of the excerpts ([chunk N]) that show the status."
    )
    evidence_quote: str | None = Field(None, max_length=400, description="Short verbatim copy from a cited excerpt.")
    explanation: NonEmptyStr = Field(max_length=400)

    @model_validator(mode="after")
    def _decision_needs_evidence(self):
        if self.status is not ComplianceStatus.UNCLEAR and not self.evidence_chunk_ids:
            raise ValueError(f"status '{self.status.value}' requires at least one evidence_chunk_id; use 'unclear' instead")
        return self


class ComplianceItem(Contract):
    """One checklist line, built by code (from a rule, or from a validated ComplianceAssessment)."""

    requirement: NonEmptyStr
    status: ComplianceStatus
    severity: Severity
    source: ItemSource
    rule_id: str | None = Field(None, description="Id of the deterministic Nepal rule that produced this item, if any.")
    evidence_chunk_ids: list[int] = Field(default_factory=list, description="kb_chunks.id values backing the status.")
    evidence_document_ids: list[int] = Field(default_factory=list, description="documents.id records backing the status.")
    evidence_ref: str | None = Field(None, description='A tender-notice field a rule relied on, e.g. "tender.deadline_ad".')
    evidence_quote: str | None = Field(None, description="Verbatim text from the cited chunk (model items).")
    explanation: str | None = None
    action_needed: str | None = Field(None, description="What the bidder must do, in plain language. Null when nothing.")
    requirement_index: int | None = Field(None, description="Index into TenderRecord.requirements (model items).")

    @model_validator(mode="after")
    def _pass_needs_evidence(self):
        cites_notice = self.rule_id is not None and (self.evidence_ref or "").startswith("tender.")
        if self.status is ComplianceStatus.PASS and not (self.evidence_chunk_ids or self.evidence_document_ids or cites_notice):
            raise ValueError("status 'pass' requires a KB chunk id or a document record; use 'unclear' instead")
        if self.source is ItemSource.RULE and self.rule_id is None:
            raise ValueError("rule items need a rule_id")
        if self.source is ItemSource.MODEL and self.rule_id is not None:
            raise ValueError("model items cannot carry a rule_id")
        return self

    @property
    def key(self) -> str:
        """Stable identity of this check, used to tell whether an override still covers a hard failure."""
        return f"{self.rule_id or 'model'}:{self.requirement}"


class ComplianceReport(Contract):
    """Rule items plus model items. Stored per tender in `compliance_items`."""

    items: list[ComplianceItem]

    @property
    def hard_failures(self) -> list[ComplianceItem]:
        return [i for i in self.items if i.status is ComplianceStatus.FAIL and i.severity is Severity.HARD]

    @property
    def is_blocked(self) -> bool:
        """Any hard failure blocks proposal generation (spec section 10.3)."""
        return bool(self.hard_failures)


class ComplianceOverrideRequest(Contract):
    """POST /tenders/{id}/compliance/override: a named person accepts the hard failures and unblocks the tender."""

    overridden_by: NonEmptyStr = Field(max_length=200, description="Who takes responsibility (no auth in the MVP).")
    reason: NonEmptyStr = Field(max_length=2000)


class ComplianceOverride(Contract):
    id: int
    overridden_by: str
    reason: str
    overridden_at: datetime
    hard_failures: list[str] = Field(description="ComplianceItem.key of every hard failure the person accepted.")
    active: bool = Field(description="True while the current report's hard failures are all among those accepted.")


class ComplianceView(Contract):
    """The compliance section of GET /tenders/{id}."""

    items: list[ComplianceItem]
    override: ComplianceOverride | None = Field(None, description="Latest override, active or not.")

    @computed_field
    @property
    def blocked(self) -> bool:
        return ComplianceReport(items=self.items).is_blocked

    @computed_field
    @property
    def hard_failures(self) -> int:
        return len(ComplianceReport(items=self.items).hard_failures)

    @computed_field
    @property
    def counts(self) -> dict[str, int]:
        return {s.value: sum(i.status is s for i in self.items) for s in ComplianceStatus}

    @computed_field
    @property
    def proposal_allowed(self) -> bool:
        """No hard failure, or an active override (CLAUDE.md: blocked -> no proposal unless overridden)."""
        return not self.blocked or bool(self.override and self.override.active)
