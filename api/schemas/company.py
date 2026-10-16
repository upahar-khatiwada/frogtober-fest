"""CompanyProfile: the bidder's own facts, entered by the user (not LLM output).

Maps onto the `company` table (spec section 11); the full object is
stored in `profile_json`.
"""

from datetime import date

from pydantic import Field

from schemas._base import Contract, FiscalYearBS, NonEmptyStr
from schemas.enums import ContractorClass, Province


class ContractorLicence(Contract):
    licence_type: NonEmptyStr = Field(description='e.g. "construction", "electrical", "municipal business".')
    licence_class: ContractorClass | None = Field(None, description="Construction licence class, if applicable.")
    licence_number: str | None = None
    issuing_body: str | None = None
    last_renewed_fy_bs: FiscalYearBS | None = Field(
        None, description="Construction licences are renewed every fiscal year (NEPAL_CONTEXT.md section 3)."
    )


class AnnualTurnover(Contract):
    fiscal_year_bs: FiscalYearBS
    amount_npr: int = Field(ge=0)


class JVPartner(Contract):
    name: NonEmptyStr
    pan_number: str | None = None
    notes: str | None = None


class CompanyProfile(Contract):
    name: NonEmptyStr
    sectors: list[str] = Field(default_factory=list)
    services: str = ""
    location: str | None = None
    province: Province | None = None
    districts_served: list[str] = Field(default_factory=list)

    pan_number: str | None = None
    vat_number: str | None = None
    registration_date: date | None = Field(None, description="Company registration date (AD).")

    licences: list[ContractorLicence] = Field(default_factory=list)
    turnover: list[AnnualTurnover] = Field(default_factory=list, description="One entry per BS fiscal year.")
    certifications: list[str] = Field(default_factory=list)
    jv_partners: list[JVPartner] = Field(default_factory=list)
