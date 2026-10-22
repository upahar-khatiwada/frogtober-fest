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
    COMPANY_PROFILE = "company_profile"  # capability statement: services, projects, personnel, equipment
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


class TenderSource(StrEnum):
    """Where POST /tenders/scrape gets raw notices from. Not a DB column."""

    SEED = "seed"  # data/seed_tenders/ (synthetic; the demo source)
    KANKAI = "kankai"  # live: kankaimun.gov.np public procurement notice board


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


class RunStatus(StrEnum):
    """A pipeline run (`pipeline_runs`, GET /runs): one orchestrated pass over one tender."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"  # reached its target status
    STOPPED = "stopped"  # ended on a branch (skipped / blocked): a normal outcome, not an error
    FAILED = "failed"  # a stage failed, crashed, or the worker was interrupted


class StageStatus(StrEnum):
    """One stage inside a pipeline run (`pipeline_runs.stages[]`). JSONB only, so no CHECK constraint."""

    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    BRANCHED = "branched"  # the stage ran and took the skipped/blocked branch
    FAILED = "failed"
    NOT_RUN = "not_run"  # an earlier stage branched or failed, or the run was interrupted first


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class ProposalLanguage(StrEnum):
    """Language a proposal is written in: the notice's language (`mixed` -> ne) unless English is forced."""

    EN = "en"
    NE = "ne"


class SectionFlagKind(StrEnum):
    """Why a proposal section needs a person's attention. JSONB only, so no CHECK constraint."""

    NO_KB_MATERIAL = "no_kb_material"  # retrieval found nothing: no model call, a stub body instead
    UNGROUNDED = "ungrounded"  # the model cited no chunk that was shown to it
    UNKNOWN_CITATION = "unknown_citation"  # a cited chunk id was not among the excerpts shown (dropped)
    UNSOURCED_FIGURE = "unsourced_figure"  # an amount / id / long number the model wrote itself (masked)
    MISSING_VALUE = "missing_value"  # a placeholder whose company/tender value is not on record
    UNKNOWN_PLACEHOLDER = "unknown_placeholder"
    FACT_NOT_VERBATIM = "fact_not_verbatim"  # a {{fact.x}} whose quote is not in its cited chunk
    GAPS_REPORTED = "gaps_reported"  # the model listed information the excerpts lacked


class SectionProgress(StrEnum):
    """Per-section progress of a running Proposal stage (`StageRun.progress`)."""

    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FLAGGED = "flagged"
    FAILED = "failed"


class MatchDecision(StrEnum):
    PURSUE = "pursue"
    SKIP = "skip"


class SignalSource(StrEnum):
    """Who produced a match signal: deterministic code (hard rule 5) or the model's judgement."""

    DETERMINISTIC = "deterministic"
    MODEL = "model"


class ComplianceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"


class ItemSource(StrEnum):
    """Which Compliance layer produced an item: a deterministic Nepal rule, or the model's KB judgement."""

    RULE = "rule"
    MODEL = "model"


class Severity(StrEnum):
    HARD = "hard"  # a fail blocks proposal generation
    SOFT = "soft"


class IngestStatus(StrEnum):
    """Knowledge-base ingestion state of an uploaded company document."""

    PENDING = "pending"  # stored, waiting for the background ingest
    PROCESSING = "processing"
    READY = "ready"  # parsed, chunked and embedded
    NEEDS_OCR = "needs_ocr"  # scanned PDF with no extractable text (no OCR in MVP)
    FAILED = "failed"  # parse or embedding error; see ingest_error


class ReviewVerdict(StrEnum):
    """Computed by code (agents.review.decide_verdict). JSONB only, so no CHECK constraint."""

    PASS = "pass"
    NEEDS_WORK = "needs_work"  # approvable, but the person should fix the listed gaps first
    FAIL = "fail"  # cannot be approved (deadline passed, a mandatory requirement unanswered, or a score too low)


class ReviewCheckId(StrEnum):
    """Deterministic Review checks (hard rule 5). JSONB only."""

    MANDATORY_ADDRESSED = "mandatory_addressed"  # every mandatory requirement is answered by a drafted section
    NO_PLACEHOLDERS = "no_placeholders"  # no [MISSING]/[UNKNOWN]/[UNVERIFIED]/⟦unsourced⟧/{{...}} left in the text
    BID_SECURITY_STATED = "bid_security_stated"  # the notice asks for bid security and the text says it is enclosed
    DEADLINE_NOT_PASSED = "deadline_not_passed"
    SECTIONS_CITED = "sections_cited"  # every section cites at least one KB chunk (hard rule 8)


class GapSource(StrEnum):
    CHECK = "check"  # a deterministic Review check
    MODEL = "model"  # the Review model's judgement


class ChecklistStatus(StrEnum):
    """An attachment-checklist row in the bid package (export/content.py). Not a DB column."""

    PRESENT = "present"  # a readable, unexpired document is on file and stays valid through the bid validity
    EXPIRING = "expiring"  # on file and valid at the deadline, but lapses before the bid validity period ends
    MISSING = "missing"  # nothing usable on file (none, expired, wrong fiscal year, or a per-bid form to sign)
