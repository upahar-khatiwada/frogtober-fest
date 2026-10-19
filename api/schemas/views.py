"""API response shapes that combine stage contracts (spec section 10.2)."""

from datetime import date, datetime

from pydantic import Field

from schemas._base import Contract, FiscalYearBS
from schemas.company import CompanyProfile
from schemas.compliance import ComplianceReport
from schemas.enums import (BuyerLevel, DocType, IngestStatus, MatchDecision, NoticeLanguage, ProcurementMethod,
                           ProcurementType, Province, TenderSource, TenderStatus)
from schemas.match import MatchResult
from schemas.tender import TenderRecord


class DeadlineView(Contract):
    """A submission deadline in both calendars. All values computed by code (nepal.dates), never the LLM."""

    ad: datetime = Field(description="Aware NPT (UTC+05:45) datetime.")
    ad_date: date = Field(description="The deadline's calendar date in NPT.")
    bs: str = Field(description="BS YYYY-MM-DD (lookup-table conversion).")
    bs_long: str = Field(description='e.g. "5 Mangsir 2083".')
    bs_ne: str = Field(description="Nepali (Devanagari) form of bs_long.")
    days_left: int = Field(description="Calendar days from today (NPT) to the deadline date; negative once passed.")
    passed: bool = Field(description="The deadline instant is at or before now (NPT).")


class TenderDetail(Contract):
    id: int
    source_url: str | None = None
    status: TenderStatus
    deadline: datetime | None = None
    deadline_view: DeadlineView | None = None
    record: TenderRecord | None = None
    match: MatchResult | None = None
    compliance: ComplianceReport | None = None


class TenderListItem(Contract):
    """One row of the ranked GET /tenders list."""

    rank: int = Field(ge=1)
    id: int
    status: TenderStatus
    title: str | None = None
    buyer: str | None = None
    buyer_level: BuyerLevel | None = None
    procurement_type: ProcurementType | None = None
    method: ProcurementMethod | None = None
    province: Province | None = None
    district: str | None = None
    language: NoticeLanguage | None = None
    estimated_cost_npr: int | None = None
    deadline: DeadlineView | None = None
    score: int | None = Field(None, description="Match score; null until Matching has run.")
    decision: MatchDecision | None = None
    reasons: list[str] = Field(default_factory=list)
    needs_review: bool = False
    source_url: str | None = None


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


class ScrapeRequest(Contract):
    """POST /tenders/scrape body. Defaults load the synthetic seed set (the demo source)."""

    source: TenderSource = TenderSource.SEED
    max_pages: int = Field(1, ge=1, le=3, description="Live source only: listing pages to read.")
    max_notices: int = Field(3, ge=1, le=10, description="Live source only: notice pages to fetch (>= 10 s apart).")


class SkippedNotice(Contract):
    url: str
    reason: str


class ScrapeReport(Contract):
    """Outcome of one load. Tenders are stored as raw text with status `new`; Scout extracts later."""

    source: TenderSource
    created: int
    updated: int = Field(description="raw_text changed: reset to status new and derived fields cleared.")
    unchanged: int
    tender_ids: list[int]
    skipped: list[SkippedNotice] = Field(default_factory=list)
    blocked: str | None = Field(None, description="Live source only: why the run stopped early (robots, 403/429, unreachable).")
