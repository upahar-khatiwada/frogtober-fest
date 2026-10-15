"""Shared Pydantic models for all pipeline stages (spec section 8.1).

TODO (next prompt): TenderRecord, MatchResult, ComplianceReport,
ProposalSection, ReviewReport - using the field suggestions in
docs/NEPAL_CONTEXT.md (e.g. TenderRecord.procurement_type,
bid_security_amount, required_docs[]). These are the contract between
stages: code routes, filters, blocks and gates on them (CLAUDE.md
"each stage emits typed JSON").
"""