"""Enums shared by the stage contracts.

The Nepal-specific enums are documented, with sources, in
docs/NEPAL_CONTEXT.md section 11. Keep the two in sync.
"""

from enum import StrEnum


# --- Nepal procurement (NEPAL_CONTEXT.md sections 1-3, 8) ---


class ProcurementType(StrEnum):
    GOODS = "goods"
    WORKS = "works"
    CONSULTING = "consulting"
    NON_CONSULTING = "non_consulting"
    UNKNOWN = "unknown"


class ProcurementMethod(StrEnum):
    NCB = "ncb"  # national competitive (open) bidding
    ICB = "icb"  # international competitive (open) bidding
    EOI = "eoi"  # expression of interest (consulting short-listing)
    RFP = "rfp"  # request for proposals (consulting)
    QUOTATION = "quotation"  # sealed quotation
    OTHER = "other"


class BuyerLevel(StrEnum):
    FEDERAL = "federal"
    PROVINCE = "province"
    LOCAL = "local"
    OTHER = "other"


class Province(StrEnum):
    # [VERIFY] names per NEPAL_CONTEXT.md section 8.
    KOSHI = "koshi"
    MADHESH = "madhesh"
    BAGMATI = "bagmati"
    GANDAKI = "gandaki"
    LUMBINI = "lumbini"
    KARNALI = "karnali"
    SUDURPASHCHIM = "sudurpashchim"


class NoticeLanguage(StrEnum):
    EN = "en"
    NE = "ne"
    MIXED = "mixed"


class EvaluationMethod(StrEnum):
    LOWEST_EVALUATED = "lowest_evaluated"  # goods/works/services, PPA section 25
    QCBS = "qcbs"  # quality and cost based selection, PPR Rule 74
    QBS = "qbs"  # quality based selection
    FIXED_BUDGET = "fixed_budget"  # budget ceiling stated in the RFP
    LEAST_COST = "least_cost"
    OTHER = "other"


class DocType(StrEnum):
    """Normalised eligibility/qualification document types (PPR Rule 40(2) + real notices)."""

    COMPANY_REGISTRATION = "company_registration"
    BUSINESS_LICENCE = "business_licence"
    LICENCE_RENEWAL = "licence_renewal"
    PAN_VAT = "pan_vat"
    TAX_CLEARANCE = "tax_clearance"
    TAX_RETURN = "tax_return"
    SELF_DECLARATION = "self_declaration"
    POWER_OF_ATTORNEY = "power_of_attorney"
    BID_SECURITY = "bid_security"
    AUDIT_REPORT = "audit_report"
    EXPERIENCE_CERTIFICATE = "experience_certificate"
    JV_AGREEMENT = "jv_agreement"
    OTHER = "other"


class RequirementCategory(StrEnum):
    ELIGIBILITY = "eligibility"
    FINANCIAL = "financial"
    EXPERIENCE = "experience"
    TECHNICAL = "technical"
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    OTHER = "other"


class ContractorClass(StrEnum):
    # Construction licence classes (NEPAL_CONTEXT.md section 3). Limits per
    # class are deliberately NOT encoded: sources conflict [VERIFY].
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# --- Pipeline ---


class Stage(StrEnum):
    SCOUT = "scout"
    MATCHING = "matching"
    COMPLIANCE = "compliance"
    PROPOSAL = "proposal"
    REVIEW = "review"


class TenderStatus(StrEnum):
    """Spec section 10.3 state machine."""

    NEW = "new"
    EXTRACTED = "extracted"
    MATCHED = "matched"
    CHECKED = "checked"
    DRAFTED = "drafted"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    SKIPPED = "skipped"  # match score below threshold
    BLOCKED = "blocked"  # hard compliance failure
    FAILED = "failed"  # a stage's LLM output was invalid after one retry


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class MatchDecision(StrEnum):
    PURSUE = "pursue"
    SKIP = "skip"


class ComplianceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"


class Severity(StrEnum):
    HARD = "hard"  # a fail blocks proposal generation
    SOFT = "soft"


class ReviewVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
