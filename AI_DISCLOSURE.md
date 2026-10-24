# AI usage disclosure

Two separate questions: how AI is used **in the product** (spec §15.1, below), and how AI was used **to build it**
(last section). Every path and function name in this file was checked against the code with `grep` on 2026-10-24
(commands at the end); line numbers are for that commit and will drift.

## 1. Where AI output is consumed programmatically (spec §15.1)

All model calls go through `api/pipeline/llm.py::LLMClient.chat` / `embed`: open-weight models only
(`qwen2.5:7b-instruct` for chat, `bge-m3` for embeddings, served by Ollama).

| File / function | What the model produces | Where code consumes it programmatically |
|---|---|---|
| [`api/agents/scout.py::extract_tender`](api/agents/scout.py#L386) (prompt: `SYSTEM_PROMPT`, line 63) | `TenderExtraction`: verbatim `{value, quote}` strings | Parsed by [`postprocess`](api/agents/scout.py#L335) into a `TenderRecord` (the deadline and amounts are converted by `nepal.parse_deadline` / `parse_npr`, never by the model). [`apply_record`](api/agents/scout.py#L395) writes `tenders.deadline_bs`, `estimated_cost_npr`, `district`, `language` and `record_json`, and [`run_scout`](api/agents/scout.py#L411) sets status `extracted`. Those columns drive the `GET /tenders` filters ([`api/routers/tenders.py`](api/routers/tenders.py#L137)) and the deadline and cost signals in Matching. |
| [`api/agents/matching.py::score_tender`](api/agents/matching.py#L220) (model call: [`assess`](api/agents/matching.py#L183)) | `MatchAssessment`: scope-relevance score 0-100 and reasons | [`combine`](api/agents/matching.py#L192) mixes it with the deterministic signals and decides `pursue` or `skip`. [`run_matching`](api/agents/matching.py#L261) stores the `matches` row and sets `matched` or `skipped` (line 298). The score orders `GET /tenders` (`Match.score.desc()`, [`api/routers/tenders.py` line 185](api/routers/tenders.py#L185)). The orchestrator runs Compliance only on a `matched` tender (`STEPS`, [`api/pipeline/orchestrator.py`](api/pipeline/orchestrator.py#L82)). |
| [`api/agents/compliance.py::check_requirements`](api/agents/compliance.py#L187) (model call: [`assess`](api/agents/compliance.py#L125)) | `ComplianceAssessment`: status, chunk ids, quote, explanation for ONE requirement | [`ground`](api/agents/compliance.py#L132) downgrades any pass or fail the evidence does not support to `unclear`. The items become a `ComplianceReport`; [`run_compliance`](api/agents/compliance.py#L300) stores them and sets `blocked` when `report.is_blocked` (any hard-severity `fail`, line 340). [`proposal_allowed`](api/agents/compliance.py#L362) gates `POST /tenders/{id}/proposal` (409). |
| [`api/agents/proposal.py::generate_section`](api/agents/proposal.py#L492) | `ProposalSectionDraft`: body with placeholders, cited chunk ids, verbatim facts | [`build_section`](api/agents/proposal.py#L448) drops unshown citations, checks facts verbatim, resolves placeholders and masks unsourced figures, and builds `ProposalSection` with `cited_chunk_ids`. [`run_proposal`](api/agents/proposal.py#L629) stores a new `proposals` version and sets `drafted`. [`api/export/content.py`](api/export/content.py#L535) assembles the document from the sections and prints each section's citations, and [`api/export/package.py`](api/export/package.py#L141) writes them into the audit summary. |
| [`api/agents/review.py::review_proposal`](api/agents/review.py#L216) | `ReviewAssessment`: three 0-100 scores and gaps tied to a section key or requirement index | [`decide_verdict`](api/agents/review.py#L154) (code) sets `pass`, `needs_work` or `fail`; [`run_review`](api/agents/review.py#L276) stores the report and sets `reviewed`. Gaps feed [`revision_feedback`](api/agents/review.py#L237) and `proposal.revise_proposal` (the automatic revision pass). [`approval_blockers`](api/agents/review.py#L335) refuses approval on a `fail` verdict. |
| [`api/ingest/embed.py::embed_chunks`](api/ingest/embed.py#L15) | bge-m3 vectors (1024 dimensions) | Called by [`ingest_document`](api/ingest/kb.py#L86) and written to `kb_chunks.embedding`. [`api/db/search.py::search_chunks`](api/db/search.py#L32) / [`retrieve`](api/db/search.py#L73) run the pgvector top-k used for retrieval in Matching, Compliance and Proposal. |

Every one of these calls writes an `agent_runs` row (stage, model, input hash, output JSON, latency, ok), shown on
the `/runs` page and in `GET /agent-runs`. Spec §15.1 listed placeholder function names; the table above uses the
real names. Differences from the spec's table: Compliance is one call per requirement (not one list), and
Matching's decision is computed by code from the model's score rather than emitted by the model.

## 2. What is code and what is model

The rule (CLAUDE.md hard rules 4, 5, 7, 8): the model fills a narrow, schema-constrained JSON model; code decides
everything that is a date, an amount, an expiry, a threshold, a gate or a verdict.

### Deterministic code (no model, unit-tested offline)

| Area | Code | What it decides |
|---|---|---|
| Dates | [`api/nepal/dates.py`](api/nepal/dates.py): `parse_deadline`, `bs_to_ad`, `ad_to_bs`, `fiscal_year_of`, `days_left` | Deadline in BS and AD (`nepali-datetime` lookup table), NPT clock, fiscal year, days left. Date-only deadlines are end of day NPT. Ambiguity gives null plus a review flag, never a guess. |
| Amounts | [`api/nepal/numbers.py`](api/nepal/numbers.py): `parse_npr`, `parse_percent`, `parse_days` | Lakh/crore grouping, Devanagari digits, compound amounts ("32 lakh 50 thousand"); mis-grouped or unit-less figures are rejected. |
| Locations and documents | [`api/nepal/geography.py`](api/nepal/geography.py), [`api/nepal/documents.py`](api/nepal/documents.py): `normalize_location`, `classify_document`, `find_fiscal_years` | 77 districts and 7 provinces in English and Nepali; document type and fiscal year from text. |
| Grounding of Scout output | `agents/scout.py::Grounder`, `postprocess` | A value counts only if its raw string and quote occur in the notice (tolerant of whitespace, case, digit script, quote style). |
| Security | [`api/nepal/rules.py::calc_bid_security`](api/nepal/rules.py#L97), `calc_performance_security` | Amount (fixed in the notice, or the notice's own percentage rounded up) and valid-until date from the notice only. No statutory percentage is ever applied. |
| Compliance rules | [`api/nepal/rules.yaml`](api/nepal/rules.yaml) + `rules.py::evaluate_rules` | 14 rules: deadline not passed, registration and licence, PAN/VAT, tax clearance for the notice's fiscal year, licence renewal, turnover, experience, bid and performance security, JV, domestic preference, document validity over the bid validity, other mandatory documents. Document expiry compared with the deadline in code. |
| Routing of requirements | `compliance.py::covering_rules`, `needs_model` | Which requirements the rules cover and which go to the model. |
| Matching | `matching.py::deterministic_signals`, `combine` | Hard skips (procurement type, district served, cost over 2x average turnover, deadline passed), 100 fit points, the 0.6/0.4 mix, the threshold and the decision. |
| Gates | `compliance.py::proposal_allowed`, `override_block`, `ComplianceReport.is_blocked` | Hard failures block Proposal; an override records who, why and which failures. |
| Proposal structure | `proposal.py::plan_sections`, `placeholder_values`, `build_section`, `proposal_language` | Which sections, in what order; every company and tender fact is inserted from the records; unsourced figures masked; language and BS/AD dates. |
| Review | `review.py::run_checks`, `decide_verdict`, `approve_proposal` | Mandatory requirements addressed, no placeholders left, bid security stated, deadline not passed, sections cited; the verdict; the approval gates. |
| Orchestration and export | `pipeline/orchestrator.py` (`TRANSITIONS`, `resume_status`), `export/content.py::build_checklist`, `export/package.py` | State machine, resume, attachment checklist (present / expiring / missing) and the package. |

### Model (Qwen2.5-7B-Instruct, temperature fixed per stage) and what it may do

| Stage | Model's job | Temperature | What it may not do |
|---|---|---|---|
| Scout | Copy strings from the notice, verbatim, with a supporting quote, and judge a few enums (type, method, buyer level, evaluation method, JV, domestic preference), each with a quote | 0 | Convert dates or amounts; emit a typed record. |
| Matching | Rate how well the tender's scope fits the company's work, with reasons | 0 | See deadline, cost or location (the prompt withholds them); decide pursue or skip. |
| Compliance | For one requirement the rules do not cover: pass, fail or unclear, citing a retrieved chunk and quoting it | 0 | Set severity or a rule id; pass without a chunk. |
| Proposal | Write prose for one section from retrieved KB chunks, citing chunk ids | 0.4 | Type facts: ids, amounts, dates and names come from placeholders or verbatim KB quotes; a figure it types is masked. |
| Review | Score completeness, relevance and compliance 0-100; list gaps tied to a real section or requirement | 0 | Set the verdict. |
| Embeddings (`bge-m3`) | Vectors for retrieval | n/a | |

Open-weight only is enforced by `api/tests/test_no_proprietary.py`.

### Rules marked unverified

In [`rules.yaml`](api/nepal/rules.yaml), 9 of 14 rules are `verified: true` (deadline, registration documents, bid
forms, PAN/VAT, tax clearance, bid security, performance security, JV, other documents) and 5 are
`verified: false`: `NP-LICENCE-RENEWAL`, `NP-TURNOVER`, `NP-EXPERIENCE`, `NP-DOMESTIC-PREF`, `NP-DOC-VALIDITY`.
"Verified" means checked against the Rules text the team could read (the 2008 English translation), not against
current law; see [`docs/NEPAL_CONTEXT.md`](docs/NEPAL_CONTEXT.md) §0 and §10. The UI shows the unverified badge.

## 3. How AI was used to build Tenderly

The code, tests and documentation were written with an AI coding assistant, prompted step by step. Each prompt's
scope, decisions and results are logged in [`PROGRESS.md`](PROGRESS.md), and the project rules the assistant worked
under are in [`CLAUDE.md`](CLAUDE.md). The runtime open-weight-only rule applies to the product's model calls; it does
not apply to development tooling. Labels in `data/golden/` and the synthetic data were written for this project;
nothing in the repository is real company or tender data. The Nepali UI labels and proposal text were produced by a
model and have not been reviewed by a native speaker.

## Verification commands

```bash
grep -rn "def extract_tender\|def postprocess\|def apply_record\|def run_scout" api/agents/scout.py
grep -rn "def score_tender\|def assess\|def combine\|def run_matching" api/agents/matching.py
grep -rn "def check_requirements\|def ground\|def run_compliance\|def proposal_allowed" api/agents/compliance.py
grep -rn "def generate_section\|def build_section\|def run_proposal" api/agents/proposal.py
grep -rn "def review_proposal\|def decide_verdict\|def run_review\|def approval_blockers" api/agents/review.py
grep -rn "def embed_chunks" api/ingest/embed.py && grep -rn "embed_chunks(" api/ingest/kb.py
grep -rn "def search_chunks\|def retrieve" api/db/search.py
```
