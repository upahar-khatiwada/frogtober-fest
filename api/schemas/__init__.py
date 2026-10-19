"""Shared Pydantic models for all pipeline stages (spec section 8.1).

These are the contract between stages: code routes, filters, blocks and
gates on them. Models the LLM fills (passed as `schema=` to
`pipeline.llm.LLMClient.chat`): TenderExtraction, MatchAssessment,
ComplianceAssessment, ProposalSection, ReviewReport. The rest are built
by code or entered by the user.
"""

from schemas.company import AnnualTurnover, CompanyProfile, ContractorLicence, JVPartner
from schemas.compliance import ComplianceAssessment, ComplianceFinding, ComplianceItem, ComplianceReport
from schemas.enums import (
    BuyerLevel,
    ComplianceStatus,
    ContractorClass,
    DocType,
    EvaluationMethod,
    IngestStatus,
    MatchDecision,
    NoticeLanguage,
    ProcurementMethod,
    ProcurementType,
    ProposalStatus,
    Province,
    RequirementCategory,
    ReviewVerdict,
    Severity,
    SignalSource,
    Stage,
    TenderSource,
    TenderStatus,
)
from schemas.match import MatchAssessment, MatchResult, MatchSignal
from schemas.proposal import Proposal, ProposalSection
from schemas.review import ReviewGap, ReviewReport, ReviewScores
from schemas.runs import AgentRun, AgentRunRecord
from schemas.scout import ExtractedDoc, Grounded, TenderExtraction
from schemas.tender import (BidSecurity, FieldSource, RequiredDoc, Requirement, ReviewFlag, SecurityCalc, TenderCriteria,
                            TenderRecord)
from schemas.views import (CompanyDocumentView, CompanyView, DeadlineView, ScrapeReport, ScrapeRequest, SkippedNotice,
                           TenderDetail, TenderListItem)

__all__ = [
    "TenderExtraction",
    "TenderCriteria",
    "SecurityCalc",
    "ReviewFlag",
    "Grounded",
    "FieldSource",
    "ExtractedDoc",
    "AgentRun",
    "AgentRunRecord",
    "AnnualTurnover",
    "BidSecurity",
    "BuyerLevel",
    "CompanyDocumentView",
    "CompanyProfile",
    "CompanyView",
    "DeadlineView",
    "ComplianceAssessment",
    "ComplianceFinding",
    "ComplianceItem",
    "ComplianceReport",
    "ComplianceStatus",
    "ContractorClass",
    "ContractorLicence",
    "DocType",
    "EvaluationMethod",
    "IngestStatus",
    "JVPartner",
    "MatchAssessment",
    "MatchDecision",
    "MatchResult",
    "MatchSignal",
    "NoticeLanguage",
    "ProcurementMethod",
    "ProcurementType",
    "Proposal",
    "ProposalSection",
    "ProposalStatus",
    "Province",
    "RequiredDoc",
    "Requirement",
    "RequirementCategory",
    "ReviewGap",
    "ReviewReport",
    "ReviewScores",
    "ReviewVerdict",
    "ScrapeReport",
    "ScrapeRequest",
    "Severity",
    "SkippedNotice",
    "Stage",
    "TenderDetail",
    "TenderListItem",
    "TenderRecord",
    "TenderSource",
    "TenderStatus",
]
