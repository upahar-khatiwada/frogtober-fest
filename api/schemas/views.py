"""API response shapes that combine stage contracts (spec section 10.2)."""

from datetime import datetime

from schemas._base import Contract
from schemas.compliance import ComplianceReport
from schemas.enums import TenderStatus
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
