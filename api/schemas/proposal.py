"""Proposal stage contracts (spec section 8.1).

The LLM drafts one `ProposalSection` per call (retrieval runs per section,
spec section 10.4). Every section must cite KB chunk ids (CLAUDE.md hard rule 8).
"""

from datetime import datetime

from pydantic import Field

from schemas._base import Contract, NonEmptyStr
from schemas.enums import ProposalStatus
from schemas.review import ReviewReport


class ProposalSection(Contract):
    title: NonEmptyStr
    body: NonEmptyStr = Field(description="Section text (Markdown).")
    cited_chunk_ids: list[int] = Field(min_length=1, description="kb_chunks.id values the text is grounded in.")


class Proposal(Contract):
    """A stored proposal version (`proposals` table, spec section 11)."""

    id: int
    tender_id: int
    version: int = Field(ge=1)
    sections: list[ProposalSection]
    review: ReviewReport | None = None
    status: ProposalStatus = ProposalStatus.DRAFT
    approved_at: datetime | None = None
