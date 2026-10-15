"""Compliance agent: requirements + company profile + documents -> ComplianceReport.

TODO (next prompt): check_requirements(...) -> ComplianceReport, per-item
status/evidence/severity. Deadline, budget and document-expiry checks are
deterministic code, never LLM judgment (CLAUDE.md hard rule 5). Evidence
without a KB chunk id is "unclear", never "pass" (hard rule 8).
"""