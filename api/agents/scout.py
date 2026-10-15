"""Scout agent: raw notice text/HTML/PDF -> TenderRecord (spec section 8.1).

TODO (next prompt): extract_tender(raw_text) -> TenderRecord, calling
pipeline.llm for a JSON-schema-constrained extraction (CLAUDE.md hard
rules 3-4), at temperature 0 (hard rule 7).
"""