# PROGRESS

## Done

### Prompt 0: bootstrap memory files (2026-10-15) ✅
- Read `docs/Tenderly_spec.pdf` in full.
- Created `CLAUDE.md`: summary, demo claim, hard rules, stack (Bun / uv), repo layout (spec §10.1), session protocol, and placeholder commands.
- Created `PROGRESS.md` (this file).
- Created `docs/NEPAL_CONTEXT.md`: procurement types, methods, evaluation, eligibility documents, JV rules, bid and performance security, domestic preference, notice publication, e-GP and scraping constraints, BS calendar and fiscal year, government levels, NPR / lakh / crore / Devanagari conventions. Every figure is cited or marked `[VERIFY]`.
- No application code written.

## Decisions
- **Embedding model: `bge-m3` (1024-dim)**, per the hard rule in the Prompt 0 instructions. `kb_chunks.embedding VECTOR(1024)` is now fixed (spec §11).
- **Tender facts come from the notice, not from the law.** Bid security, validity, deadline and required documents are extracted per tender. Statutory amounts in NEPAL_CONTEXT.md are context only, because the English Rules text available is from 2008 and is outdated.
- **Scraper target:** do not scrape bolpatra.gov.np by evading blocks. Prefer public notice PDFs on entity sites, honour PPMO `Crawl-delay: 10`, and keep the seeded dataset as the primary demo source.
- **BS dates:** convert with a lookup-table library behind deterministic tests. Never use arithmetic or the LLM.

## Deviations from spec
- None yet. (The spec allowed bge-m3 *or* nomic-embed-text. Choosing bge-m3 is a selection within the spec, not a deviation.)

## Open issues
`[VERIFY]` items in `docs/NEPAL_CONTEXT.md` §10:
1. Current procurement thresholds (tender / sealed quotation / direct / EOI / ICB / review). Only the 2008 English text (2nd amendment) was parsed. The Nepali consolidated text up to the 11th amendment is linked but not parsed, and the 12th amendment was not read.
2. Current bid-security % range, and the low-bid additional performance-security formula.
3. Current bid-validity days (2008 text: 90 / 120).
4. Domestic preference % (2008 text: 10% for goods) and any margin for domestic contractors.
5. Contractor licence class limits (secondary sources conflict) and the renewal rule text.
6. bolpatra.gov.np robots.txt and ToS: robots returned 403 or a maintenance page. No open-data feed found.
7. Whether the 2082 PPA amendment bill / 2083 ordinance is in force.
8. Official confirmation of the fiscal-year start, province names, district list, and NPT UTC+05:45.
9. BS↔AD library choice.
10. PPMO blacklist URL.
11. Whether lowest-price acceptance is the general sealed-quotation rule.

Other:
- The spec's AI-disclosure table (§15.1) is garbled in the PDF text extraction. Function names will be finalised from real code.

## Next prompt
**Prompt 1:** scaffold the monorepo per CLAUDE.md layout. Set up Docker Compose (web, api, postgres+pgvector, ollama), the FastAPI skeleton (uv, Python 3.11), DB migrations for the spec §11 schema with `VECTOR(1024)`, the Next.js + TS + Tailwind + shadcn scaffold with Bun, and `api/pipeline/llm.py` with schema-constrained calls and one retry. Draft the shared Pydantic schemas (TenderRecord, MatchResult, ComplianceReport, ProposalSection, ReviewReport) using NEPAL_CONTEXT.md field suggestions. Fill in the CLAUDE.md Commands table.
