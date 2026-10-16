"""TenderRecord: the Scout stage's output (spec section 8.1).

Every value is what the notice says. Nothing is defaulted from
statutory percentages (NEPAL_CONTEXT.md section 4, "compute nothing").
Amounts are integer NPR after deterministic lakh/crore/Devanagari
normalisation (NEPAL_CONTEXT.md section 9).
"""

from datetime import datetime

from pydantic import Field, model_validator

from schemas._base import BSDateISO, Contract, FiscalYearBS, NonEmptyStr
from schemas.enums import (
    BuyerLevel,
    DocType,
    EvaluationMethod,
    NoticeLanguage,
    ProcurementMethod,
    ProcurementType,
    Province,
    RequirementCategory,
)


class BidSecurity(Contract):
    amount_npr: int | None = Field(None, ge=0, description="Fixed amount stated in the notice, in NPR.")
    percent: float | None = Field(None, gt=0, le=100, description="Percent of bid price, if stated that way.")
    validity_days: int | None = Field(None, gt=0, description="Days the bid security must stay valid.")

    @model_validator(mode="after")
    def _amount_or_percent(self) -> "BidSecurity":
        if self.amount_npr is None and self.percent is None:
            raise ValueError("bid_security needs amount_npr or percent; use null for bid_security if not stated")
        return self


class RequiredDoc(Contract):
    doc_type: DocType
    description: NonEmptyStr = Field(description="Document name as written in the notice.")
    fiscal_year_bs: FiscalYearBS | None = Field(
        None, description='BS fiscal year the document must cover, e.g. "2080/81" for tax clearance.'
    )
    mandatory: bool = True
    source_quote: str | None = Field(None, description="Verbatim text from the notice.")


class Requirement(Contract):
    text: NonEmptyStr
    mandatory: bool
    category: RequirementCategory
    source_quote: NonEmptyStr = Field(description="Verbatim text from the notice this requirement came from.")


class TenderRecord(Contract):
    title: NonEmptyStr
    reference_no: str | None = Field(None, description="IFB / notice number.")
    buyer: NonEmptyStr
    buyer_address: str | None = None
    buyer_level: BuyerLevel
    province: Province | None = None
    district: str | None = None
    location: str | None = Field(None, description="Site or delivery location as written.")
    scope: NonEmptyStr = Field(description="Short summary of what is being procured.")

    procurement_type: ProcurementType
    method: ProcurementMethod
    evaluation_method: EvaluationMethod | None = None
    language: NoticeLanguage

    deadline_ad: datetime | None = Field(
        None, description="Submission deadline in AD, Nepal Time (UTC+05:45), only if the notice states an AD date."
    )
    deadline_bs_raw: str | None = Field(None, description="Submission deadline exactly as written in BS, verbatim.")
    deadline_bs_iso: BSDateISO | None = Field(
        None,
        description="deadline_bs_raw normalised to BS YYYY-MM-DD. Overwritten by deterministic code; never trusted from the LLM.",
    )

    currency: str = Field("NPR", pattern=r"^[A-Z]{3}$")
    estimated_cost_npr: int | None = Field(None, ge=0)
    bid_security: BidSecurity | None = None
    bid_validity_days: int | None = Field(None, gt=0)
    bid_doc_fee_npr: int | None = Field(None, ge=0)
    performance_security_percent: float | None = Field(None, gt=0, le=100)
    domestic_preference: bool = False
    jv_allowed: bool | None = Field(None, description="null when the notice does not say.")

    required_docs: list[RequiredDoc] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
