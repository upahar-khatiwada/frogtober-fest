"""Proposal stage contracts (spec section 8.1).

The LLM drafts one `ProposalSectionDraft` per call (retrieval runs per section, spec section 10.4). It writes
identifiers and figures only as placeholders (`{{company.pan}}`, `{{fact.<key>}}`); code resolves them from the
company record, the tender record, or verbatim KB quotes, and builds the stored `ProposalSection`. A section
that cites no shown KB chunk is kept but flagged `ungrounded` (CLAUDE.md hard rule 8), never filled by invention.
"""

from datetime import datetime

from pydantic import Field

from schemas._base import Contract, NonEmptyStr
from schemas.enums import ProposalLanguage, ProposalStatus, SectionFlagKind
from schemas.review import ReviewReport


class SectionFact(Contract):
    """A value copied from one KB excerpt, used in the body as {{fact.<key>}}. Code checks the quote is verbatim."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$", description="Placeholder name, e.g. road_project_value.")
    chunk_id: int = Field(description="The [chunk N] the quote is copied from.")
    quote: NonEmptyStr = Field(description="Exact text copied from that excerpt (a project name, amount, number).")


class ProposalSectionDraft(Contract):
    """What the LLM fills for one section."""

    body: NonEmptyStr = Field(description="Section text (Markdown, no heading). Figures and ids only as {{placeholders}}.")
    cited_chunk_ids: list[int] = Field(description="[chunk N] numbers the text is based on; empty if none supports it.")
    facts: list[SectionFact] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list, description="Information the section needs that no excerpt gives.")


class SectionFlag(Contract):
    kind: SectionFlagKind
    detail: str


class ResolvedPlaceholder(Contract):
    name: str
    value: str | None = Field(description="Inserted text; null when the value is not on record.")
    source: str = Field(description='"company", "tender", "clock" or "chunk <id>".')


class ProposalSection(Contract):
    """A stored section (built by code from the draft)."""

    key: NonEmptyStr = Field(description="Template key, e.g. relevant_experience.")
    title: NonEmptyStr
    body: str = Field(description="Rendered text (Markdown) with placeholders resolved.")
    body_template: str = Field("", description="The model's text with placeholders, before resolution.")
    cited_chunk_ids: list[int] = Field(default_factory=list, description="Valid kb_chunks.id values the text cites.")
    grounded: bool = Field(description="At least one valid KB citation.")
    flags: list[SectionFlag] = Field(default_factory=list)
    requirement_indices: list[int] = Field(default_factory=list, description="TenderRecord.requirements this section answers.")
    placeholders: list[ResolvedPlaceholder] = Field(default_factory=list)


class Proposal(Contract):
    """A stored proposal version (`proposals` table, spec section 11)."""

    id: int
    tender_id: int
    version: int = Field(ge=1)
    language: ProposalLanguage
    sections: list[ProposalSection]
    review: ReviewReport | None = None
    status: ProposalStatus = ProposalStatus.DRAFT
    approved_at: datetime | None = None
    created_at: datetime | None = None
    citation_rate: float = Field(ge=0, le=1, description="Share of sections with at least one valid KB citation.")


class ProposalSummary(Contract):
    """Latest proposal version on the tender detail page."""

    id: int
    version: int
    language: ProposalLanguage
    status: ProposalStatus
    created_at: datetime | None = None
    sections_total: int
    sections_grounded: int
    sections_flagged: int


class ProposalRequest(Contract):
    """POST /tenders/{id}/proposal body (optional)."""

    force_english: bool | None = Field(
        None, description="Write in English whatever the notice language. Default: the PROPOSAL_FORCE_ENGLISH setting.")
