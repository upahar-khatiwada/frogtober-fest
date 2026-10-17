"""Shared Pydantic models for all pipeline stages (spec section 8.1).

These are the contract between stages: code routes, filters, blocks and
gates on them. Models the LLM fills (passed as `schema=` to
`pipeline.llm.LLMClient.chat`): TenderRecord, MatchAssessment,
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
    Stage,
    TenderStatus,
)
from schemas.match import MatchAssessment, MatchResult
from schemas.proposal import Proposal, ProposalSection
from schemas.review import ReviewGap, ReviewReport, ReviewScores
from schemas.runs import AgentRun, AgentRunRecord
from schemas.tender import BidSecurity, RequiredDoc, Requirement, TenderRecord
from schemas.views import CompanyDocumentView, CompanyView, TenderDetail

__all__ = [
    "AgentRun",
    "AgentRunRecord",
    "AnnualTurnover",
    "BidSecurity",
    "BuyerLevel",
    "CompanyDocumentView",
    "CompanyProfile",
    "CompanyView",
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
    "Severity",
    "Stage",
    "TenderDetail",
    "TenderRecord",
    "TenderStatus",
]
