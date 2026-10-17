"""API response shapes that combine stage contracts (spec section 10.2)."""

from datetime import date, datetime

from pydantic import Field

from schemas._base import Contract, FiscalYearBS
from schemas.company import CompanyProfile
from schemas.compliance import ComplianceReport
from schemas.enums import DocType, IngestStatus, TenderStatus
from schemas.match import MatchResult
from schemas.tender import TenderRecord


class TenderDetail(Contract):
    id: int
    source_url: str | None = None
    status: TenderStatus
    deadline: datetime | None = None
    record: TenderRecord | None = None
    match: MatchResult | None = None
    compliance: ComplianceReport | None = None


class CompanyView(CompanyProfile):
    """The stored company profile (single-company MVP)."""

    id: int
    updated_at: datetime


class CompanyDocumentView(Contract):
    """An uploaded KB document and its ingestion state (GET /company/documents)."""

    id: int
    filename: str
    doc_type: DocType
    expires_on: date | None = None
    is_expired: bool | None = Field(None, description="expires_on is before today (NPT). Computed by code; null if no expiry.")
    fiscal_year_bs: FiscalYearBS | None = None
    value_npr: int | None = None
    ingest_status: IngestStatus
    ingest_error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    page_count: int | None = None
    chunk_count: int = 0
    uploaded_at: datetime
