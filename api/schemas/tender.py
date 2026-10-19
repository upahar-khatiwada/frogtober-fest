"""TenderRecord: the Scout stage's output (spec section 8.1).

Every value is what the notice says. Nothing is defaulted from
statutory percentages (NEPAL_CONTEXT.md section 4, "compute nothing").
Amounts are integer NPR after deterministic lakh/crore/Devanagari
normalisation (NEPAL_CONTEXT.md section 9).

The LLM does not fill this model. It fills `schemas.scout.TenderExtraction`
(verbatim raw strings + source quotes), and `agents.scout` builds the
TenderRecord from that with the deterministic Nepal layer.
"""

from datetime import date, datetime

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


class TenderCriteria(Contract):
    """Numeric qualification criteria from the notice (Scout fills the amounts; counts when written in digits/words)."""

    min_avg_turnover_npr: int | None = Field(None, ge=0)
    turnover_years: int | None = Field(None, gt=0)
    min_similar_projects: int | None = Field(None, gt=0)
    min_similar_value_npr: int | None = Field(None, ge=0)


class SecurityCalc(Contract):
    """A security amount computed by `nepal.rules` from the notice's own figures."""

    amount_npr: int | None
    valid_until: date | None = None
    valid_until_bs: str | None = None
    basis: str


class FieldSource(Contract):
    """Where one TenderRecord value came from, so the UI can show the value next to its source."""

    field: str = Field(description='TenderRecord path, e.g. "estimated_cost_npr" or "required_docs[2]".')
    value: str | int | float | bool | None = Field(None, description="The stored value (dates as ISO strings).")
    raw: str | None = Field(None, description="Verbatim string the LLM copied from the notice.")
    quote: str | None = Field(None, description="Verbatim notice text the value is grounded in.")
    span: tuple[int, int] | None = Field(None, description="[start, end) of the quote in tenders.raw_text, if found.")
    quote_found: bool = Field(False, description="The quote (or raw value) occurs in the notice text.")


class ReviewFlag(Contract):
    """A field code could not confirm. The raw string is kept; the value is left null rather than guessed."""

    field: str
    reason: str
    raw: str | None = None


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
        None,
        description="Submission deadline as an aware NPT (UTC+05:45) datetime: the printed AD date, or the BS date "
        "converted by lookup table. Set by deterministic code; null when the deadline could not be confirmed.",
    )
    deadline_bs_raw: str | None = Field(
        None, description="Submission deadline exactly as written (verbatim), when it contains a BS date that parsed cleanly."
    )
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

    # --- code-owned (agents.scout); never from the LLM ---
    criteria: TenderCriteria = Field(default_factory=TenderCriteria)
    bid_security_due: SecurityCalc | None = Field(None, description="nepal.rules.calc_bid_security on this record.")
    sources: list[FieldSource] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    needs_review: bool = Field(False, description="True if any review_flags: a human should check those fields.")
