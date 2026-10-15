"""Matching agent: TenderRecord + company profile + KB chunks -> MatchResult.

TODO (next prompt): score_tender(...) -> MatchResult (score 0-100, reasons,
decision). The score-threshold routing (pursue/skip) is deterministic code
in the orchestrator, not LLM judgment (CLAUDE.md hard rule 5).
"""