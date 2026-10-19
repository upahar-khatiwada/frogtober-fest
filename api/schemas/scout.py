"""TenderExtraction: what the Scout LLM fills (CLAUDE.md hard rules 4-5).

The model copies strings. It never converts dates, amounts, percentages or
day counts, and never normalises document types or locations: every such
field is a `Grounded` pair of a verbatim `value` and the verbatim `quote` it
came from. `agents.scout.postprocess` turns this into a `TenderRecord` with
the deterministic Nepal layer, and checks every quote against the notice.

Classification fields (procurement type, method, buyer level, evaluation
method, JV, domestic preference) are judgments the parsers cannot make, so
the LLM picks an enum value and must quote the words it based it on.
"""

from pydantic import Field

from schemas._base import Contract, NonEmptyStr
from schemas.enums import BuyerLevel, EvaluationMethod, ProcurementMethod, ProcurementType
from schemas.tender import Requirement


class Grounded(Contract):
    value: NonEmptyStr = Field(description="The value, copied character for character from the notice.")
    quote: NonEmptyStr = Field(description="The full sentence or line of the notice that contains the value, copied verbatim.")


class ExtractedDoc(Contract):
    name: NonEmptyStr = Field(description="Document name exactly as written in the notice.")
    mandatory: bool = True
    source_quote: NonEmptyStr = Field(description="Verbatim notice text that asks for this document.")


class TenderExtraction(Contract):
    title: Grounded = Field(description="Name of the work / contract / goods as written.")
    reference_no: Grounded | None = Field(None, description="IFB / contract / notice number as written.")
    buyer: Grounded = Field(description="Procuring entity name as written.")
    buyer_address: Grounded | None = None
    location: Grounded | None = Field(None, description="Site / delivery place as written (ward, municipality, district).")
    scope: Grounded = Field(description="value: one-sentence English summary of what is procured. quote: the notice text it summarises.")

    procurement_type: ProcurementType
    procurement_type_quote: str | None = None
    method: ProcurementMethod
    method_quote: str | None = None
    evaluation_method: EvaluationMethod | None = None
    evaluation_method_quote: str | None = None
    buyer_level: BuyerLevel

    deadline: Grounded | None = Field(None, description="Bid SUBMISSION deadline date and time as written. Not publication, purchase or opening.")
    estimated_cost: Grounded | None = Field(None, description="Estimated / approximate cost as written, with currency and unit words.")
    bid_security: Grounded | None = Field(None, description="Bid security / bid bond / धरौटी amount or percentage as written.")
    bid_security_validity: Grounded | None = Field(None, description="How long the bid security must be valid, as written.")
    bid_validity: Grounded | None = Field(None, description="Bid validity period as written.")
    bid_doc_fee: Grounded | None = Field(None, description="Bid document / form fee as written.")
    performance_security: Grounded | None = Field(None, description="Performance security percentage as written.")
    min_avg_turnover: Grounded | None = Field(None, description="Minimum average annual turnover amount as written.")
    min_similar_contract_value: Grounded | None = Field(None, description="Minimum value of a similar completed contract as written.")

    jv_allowed: bool | None = Field(None, description="null if the notice does not say.")
    jv_quote: str | None = None
    domestic_preference: bool = False
    domestic_preference_quote: str | None = None

    required_docs: list[ExtractedDoc] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
