# PROGRESS

## Done

### Prompt 0: bootstrap memory files (2026-10-15) ✅
- Read `docs/Tenderly_spec.pdf` in full.
- Created `CLAUDE.md`: summary, demo claim, hard rules, stack (Bun / uv), repo layout (spec §10.1), session protocol, and placeholder commands.
- Created `PROGRESS.md` (this file).
- Created `docs/NEPAL_CONTEXT.md`: procurement types, methods, evaluation, eligibility documents, JV rules, bid and performance security, domestic preference, notice publication, e-GP and scraping constraints, BS calendar and fiscal year, government levels, NPR / lakh / crore / Devanagari conventions. Every figure is cited or marked `[VERIFY]`.
- No application code written.

### Prompt 1: scaffold the monorepo (2026-10-15) ✅
- Git repo initialized. `docs/` created holding `NEPAL_CONTEXT.md` and `Tenderly_spec.pdf` (moved from repo root, content unchanged).
- `LICENSE` (MIT), `README.md` (quick start, stack, repo layout, status), `ARCHITECTURE.md` and `AI_DISCLOSURE.md` (TODO placeholders per spec §8, §15.1).
- `api/`: FastAPI skeleton scaffolded with uv (Python 3.11). `main.py` (CORS + `/health`), `config.py` (pydantic-settings), `routers/{tenders,company,proposals,runs}.py` (route shapes from spec §10.2, every endpoint stubbed 501 pending Prompt 2's schemas/agents), `agents/{scout,matching,compliance,proposal,review}.py` and `pipeline/{llm,orchestrator}.py` (stub modules, each documenting which CLAUDE.md hard rule it owes), `schemas/` (empty, pending Prompt 2), `ingest/{scraper,parse_docs,embed}.py` and `export/{docx,pdf,package}.py` (stubs), `tests/test_health.py` (passing), `Dockerfile` + `.dockerignore`. Verified: `uv run pytest -q` passes; `/health` checked live over uvicorn and inside Docker.
- `web/`: Next.js 16 + TypeScript + Tailwind v4 + ESLint scaffolded with Bun (`bun create next-app`). shadcn/ui initialized (`bunx shadcn@latest init`) and a Button component added (`bunx shadcn@latest add button`), verified with a Vitest + Testing Library smoke test. `openapi-typescript` + `openapi-fetch` wired up: `bun run gen:api` generates `lib/api/types.ts` from the live FastAPI OpenAPI schema; `lib/api/client.ts` is the typed fetch wrapper. `Dockerfile` + `.dockerignore`. Verified: `bun run test` (2 passed), `bun run build` (clean, including type-checking against the generated API types).
- `docker-compose.yml` (web, api, db [`pgvector/pgvector:pg16` with a `pg_isready` healthcheck], ollama), `scripts/setup.sh` (pulls chat + embed models), `.env.example`. Verified with `docker compose up --build`: web returns 200, api `/health` returns ok, ollama root responds "Ollama is running", db healthcheck confirmed implicitly (api's `depends_on: condition: service_healthy` only started because db passed its healthcheck). Pulled `bge-m3` successfully to prove the model-pull mechanism works; did **not** pull the 7B chat model end-to-end (see Open issues).
- `CLAUDE.md` Commands table filled in with real, verified commands.

### Prompt 2: contract layer (2026-10-16) ✅
- `api/schemas/`: `TenderRecord` (with all the Nepal fields: procurement type/method/buyer level/province/district, AD + raw BS + normalised BS deadline, NPR amounts, `BidSecurity`, performance security %, domestic preference, JV, language, evaluation method, `RequiredDoc[]` with a normalised `DocType` and optional BS fiscal year, `Requirement[]` with category and source quote), `CompanyProfile` (PAN/VAT, registration date, `ContractorLicence[]` with class A–D and last-renewed FY, per-FY `AnnualTurnover[]`, JV partners, districts served), `MatchAssessment` → `MatchResult`, `ComplianceFinding`/`ComplianceAssessment` → `ComplianceItem`/`ComplianceReport` (`rule_id`, `is_blocked`), `ProposalSection`, `Proposal`, `ReviewReport` (scores completeness/relevance/compliance, gaps, verdict), `AgentRunRecord`/`AgentRun`, `TenderDetail`. Enums live in `enums.py` and are documented in NEPAL_CONTEXT.md §11.
- `api/pipeline/llm.py`: `LLMClient` with schema-constrained `/api/chat` (`format` = Pydantic JSON schema with `$ref`s inlined), strict Pydantic validation, one retry that feeds the validation error back, per-call timeout (`LLM_TIMEOUT_S`, default 180 s), latency capture, one `AgentRunRecord` per call through a required `run_recorder` callback (on success *and* failure), per-stage temperatures, and `embed()` via `/api/embed` with a 1024-dim check.
- Stub routes now declare request/response models (they still return 501), so the OpenAPI schema and `web/lib/api/types.ts` carry every contract. `bun run gen:api` was run and the types regenerated.
- `httpx` moved from dev to runtime dependencies.
- Tests: `uv run pytest -q` gives **44 passed, 1 deselected** (offline, `httpx.MockTransport`). They cover valid parses of every contract, retry-then-success, malformed → exactly one retry → `LLMOutputError` + failed run row, no string→int coercion, Nepal enum/format rejection (procurement type, method, buyer level, province, language, evaluation method, currency, BS date, fiscal year, doc type, contractor class), extra-field rejection, pass-without-chunk-id rejection, timeouts/HTTP errors, temperature rules, input-hash stability, and embedding dimension. `tests/test_llm_ollama_smoke.py` (`-m ollama`) was written but **not run**, because no Ollama was reachable locally.

### Prompt 3: deterministic Nepal layer (2026-10-17)
- `api/nepal/`: `numbers.py` (parse_npr, format_npr, humanize_npr, Devanagari digits), `dates.py` (BS parse/format, BS<->AD via `nepali-datetime`, NPT, fiscal year, days_left, deadline_from_raw), `geography.py` (7 provinces, 77 districts, EN+NE, spellings, normalize_location), `rules.yaml` (11 rules), `rules.py` (loader, bid/performance security calculators, evaluator returning `ComplianceItem`s with `rule_id`).
- Tests: `tests/test_nepal_{numbers,dates,geography,rules}.py`.
- Deps added: `nepali-datetime`, `pyyaml`.

### Prompt 4: database, KB ingestion, company endpoints, demo seed (2026-10-17) ✅
- **DB:** SQLAlchemy 2 models (`api/db/models.py`) + Alembic (`api/alembic.ini`, `api/alembic/`, migration `0001_initial_schema`). Covers all 8 spec §11 tables, plus `CREATE EXTENSION vector`, `kb_chunks.embedding VECTOR(1024)` with an HNSW `vector_cosine_ops` index, and CHECK constraints that mirror every enum. Nepal columns: tenders `procurement_type, method, province, district, deadline_bs, estimated_cost_npr, language`; documents `doc_type, expires_on, fiscal_year_bs, value_npr` plus ingest bookkeeping (`content` BYTEA, `sha256`, `ingest_status`, `ingest_error`, `warnings[]`, `page_count`); company `pan_number, vat_number, licence_classes[], province`. Also agent_runs `attempts/error/raw_output` and compliance_items `rule_id/explanation`.
- `db/search.py`: `search_chunks` (top-k by pgvector cosine distance, filters by company/doc_type, `ready` docs only, returns `ChunkHit` with `chunk_id` + similarity) and `retrieve` (embeds the query through `LLMClient`). `db/runs.py::make_run_recorder` writes agent_runs rows. `deps.py` provides the FastAPI dependencies.
- **Ingestion:** `ingest/parse_docs.py` handles PDF (PyMuPDF), DOCX (python-docx, paragraphs + tables) and TXT (strict UTF-8, BOM/UTF-16 OK, otherwise a `ParseError`; never mojibake). Text is NFC-normalised, only control chars are stripped, and ZWJ/ZWNJ are kept. Flags: `needs_ocr` when no page has text; warnings for partly scanned pages, legacy Nepali fonts (Preeti etc.) and garbled conjuncts. `ingest/chunking.py` makes 400-600 estimated-token chunks with 80 overlap and splits on `.!?` and the danda. `ingest/embed.py::embed_chunks` batches through `LLMClient.embed`. `ingest/kb.py` covers create, parse, chunk, embed and `kb_chunks`, records the status, and is re-runnable.
- **Endpoints:** `POST /company` (upsert of the single company), `GET /company`, `POST /company/documents` (multipart: `file`, `doc_type`, optional `expires_on` AD or `expires_on_bs` converted deterministically, `fiscal_year_bs`, `value_npr`; 202 + background ingest; 404/413/415/422/400 errors), `GET /company/documents` (status, chunk_count, warnings, computed `is_expired` against today in NPT).
- **Demo data:** `data/demo_company/` holds `profile.json` (Annapurna Demo Nirman Sewa Pvt. Ltd., fictional, Pokhara, class C, turnover in NPR) and `manifest.json`, plus 5 documents: registration TXT (bilingual, **valid** to 2084-03-32 BS = 2027-07-16), PAN/VAT DOCX, tax clearance PDF for FY 2081/82 (**expired** 2083-03-32 BS = 2026-07-16), experience certificate DOCX (Rs 1,85,40,000) and a 2-page company profile PDF. All are marked FICTIONAL. `scripts/build_demo_docs.py` regenerates the binaries, and `scripts/seed_demo.py` seeds them.
- Schemas: `DocType.company_profile`, `IngestStatus`, `CompanyView`, `CompanyDocumentView`. `web/lib/api/types.ts` regenerated.
- `api/Dockerfile`: runs `alembic upgrade head` before `fastapi run`, and installs with `--no-dev`.
- Deps: `sqlalchemy` 2.1, `alembic`, `psycopg[binary]`, `pgvector`, `pymupdf`, `python-docx`, `python-multipart`; dev: `pgserver` (embedded Postgres + pgvector for tests; no network/API use).
- Fixed a wrong assertion in `tests/test_nepal_dates.py` (Chaitra 2082 is FY 2082/83, not 2081/82). It failed on clean HEAD, and the code was right.
- **Verified:** `uv run pytest -q` gives **290 passed, 1 deselected**. That includes 19 DB/API tests + 1 seed test on a real Postgres+pgvector (pgserver): `alembic check` finds no model/migration drift, downgrade/upgrade round-trips, the column is `vector(1024)`, CHECKs reject bad enums, cosine ordering + filters work, the upload flow covers ready / needs_ocr / failed, and seed + retrieval pass. `alembic upgrade head` and `python -m scripts.seed_demo` were run from the CLI against a scratch DB. Seed exits 1 with `failed` docs when Ollama is down, as designed. **Not verified:** seed with real bge-m3 embeddings (no Ollama here) and the Docker image build (no Docker on this machine).


## Decisions
- **Embedding model: `bge-m3` (1024-dim)**, per the hard rule in the Prompt 0 instructions. `kb_chunks.embedding VECTOR(1024)` is now fixed (spec §11).
- **Tender facts come from the notice, not from the law.** Bid security, validity, deadline and required documents are extracted per tender. Statutory amounts in NEPAL_CONTEXT.md are context only, because the English Rules text available is from 2008 and is outdated.
- **Scraper target:** do not scrape bolpatra.gov.np by evading blocks. Prefer public notice PDFs on entity sites, honour PPMO `Crawl-delay: 10`, and keep the seeded dataset as the primary demo source.
- **BS dates:** convert with a lookup-table library behind deterministic tests. Never use arithmetic or the LLM.
- **shadcn/ui's current architecture (as of Oct 2026) differs from what older docs/training data assume**: `bunx shadcn@latest init` now ships `cn` and base theme CSS as installable npm packages (`cn`, `shadcn/tailwind.css`) rather than copy-pasted boilerplate, and components use `@base-ui/react` instead of Radix primitives. `components.json`'s `style` field is now `"base-nova"`. Takeaway: always run the real CLI and check its actual output rather than hand-writing shadcn components from memory.
- **`fastapi[standard]` extra is required**, not plain `fastapi` — `fastapi dev`/`fastapi run` (used locally and in `api/Dockerfile`'s CMD) need the bundled `fastapi-cli`, which only ships via the `[standard]` extra.
- **`api/`'s project layout is flat "app" style, not "library" style.** A bare `uv init --name tenderly-api` on newer uv versions can default to a `src/`-layout installable package (with a `[build-system]` section); we deliberately flattened it to match CLAUDE.md's repo layout (`api/main.py`, `api/routers/`, etc.), since nothing here is meant to be built/installed as a package.

- **LLM output models are separate from code-decided models (Prompt 2).** The LLM never emits a decision that hard rule 5 reserves for code. `MatchAssessment` has no `decision` (it is computed from the threshold), and `ComplianceFinding` has no `rule_id`, so the LLM can't pose as a deterministic rule to get a chunk-less `pass` through.
- **Validation is strict.** `extra="forbid"` on every contract, plus `model_validate_json(strict=True)` in the client, so `"72"` for an int or an invented key fails and is retried rather than coerced.
- **`deadline_bs_iso` is code-owned.** It is in `TenderRecord` (so it is stored), but the Scout must overwrite it from `deadline_bs_raw` with the deterministic normaliser.
- **`jv_allowed` and `evaluation_method` are nullable**, because "the notice is silent" is a real third state. `procurement_type` gets `unknown` (per NEPAL_CONTEXT §1).
- **Added `TenderStatus.failed`** for hard rule 4 / spec §10.5 "clear failed state".
- **Embedding calls write no agent_runs row.** They are not an agent stage, and ingest would otherwise log one row per chunk.
- **The client is synchronous** (httpx `Client`). Agents will run in background jobs (APScheduler), so async adds nothing yet.
- Security amounts and validity come from the notice only. No statutory % or +30 days. Validity is counted from the submission deadline (assumption, unverified).
- Rule thresholds for turnover/experience come from `TenderCriteria` (notice), not statute.
- "Pass" needs evidence (chunk id from document metadata, or a named profile/notice field). Enforced in one place (`rules.o`).
- Missing document of a required type is `fail`; document present without chunk id is `unclear`.
- Bid/performance security, licence renewal, JV, domestic preference are `soft`.
- `parse_npr` is strict: one number, NPR only, no fractional rupees.
- Date-only BS deadlines are end of day NPT (23:59:59).
- **Embedding dimension fixed at 1024 (bge-m3) in migration 0001.** A model change needs a migration and a re-embed.
- **Enum columns are TEXT + CHECK**, not native PG enums. Constraint values are frozen in each migration, so a new enum value means a new migration (alembic check catches the drift).
- **Token counts are estimated** (about 4 chars/token for Latin, 2 for Devanagari, 1 per punctuation mark) instead of shipping bge-m3's tokenizer. 400-600 is retrieval granularity, far below bge-m3's 8192 limit. Every chunk except the last is guaranteed 400-600; the last may be shorter.
- **Ingestion is a FastAPI BackgroundTask**, and its state lives on the row (`ingest_status`). APScheduler isn't needed for this. The upload returns 202 and the UI polls `GET /company/documents`.
- **Originals are stored in `documents.content` (BYTEA)**, so the export package can attach them without a shared volume (uploads capped at 20 MB).
- **Single company:** `POST /company` upserts the lowest-id row (multi-tenant is out of scope).
- **`is_expired` is computed in code** (expires_on < today NPT, hard rule 5). Expiry can be entered in BS and is converted with `nepal.dates`.
- **Demo PDFs are English-only.** PyMuPDF-written Devanagari loses conjuncts on extraction, so Devanagari lives in the TXT/DOCX demo docs.
- **DB tests run by default** on an embedded pgserver Postgres, or on `TEST_DATABASE_URL`. They skip only if neither is available.

## Deviations from spec
- §11 `tenders.budget` is named `estimated_cost_npr` (same meaning, integer NPR). Timestamps are `TIMESTAMPTZ`, not `TIMESTAMP` (NPT matters). `matches` has a serial `id` (spec has no PK). `agent_runs.tender_id` has no FK, as in the spec, because Scout runs before the tender row exists.
- `DocType.company_profile` added (capability statement; NEPAL_CONTEXT §11 updated).
- None in behaviour. Additive fields beyond §8.1/§11: `TenderStatus.failed`, `AgentRunRecord.attempts/error/raw_output` (the `agent_runs` table needs these three columns when migrations land), `ReviewGap.severity`, `ComplianceItem.explanation`. (The spec allowed bge-m3 *or* nomic-embed-text; choosing bge-m3 is a selection within the spec.)
none known, spec §8.2/§13 not re-read in this session (PDF not available to me)

## Open issues
`[VERIFY]` items in `docs/NEPAL_CONTEXT.md` §10 (unchanged from Prompt 0):
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
16. Verify spec §8.2 and §13 against api/nepal/ (not read this session).
17. ~~`nepali-datetime` tests not run~~: run in Prompt 4. All pass after fixing one wrong test assertion. The library range (about 1975-2100 BS) is still its own limit.
18. `TenderRecord` has no structured turnover/experience criteria; `TenderCriteria` is passed separately. Scout should extract them.
19. `CompanyProfile` has no project history; experience comes from `DocumentMeta` (`similar`, `value_npr`). The `documents` table now holds `doc_type/expires_on/fiscal_year_bs/value_npr`. Still missing: a loader that turns `documents` rows into `DocumentMeta` (which chunk id cites a document? its first chunk?) and the `similar` classification.
20. Bid-security validity start date (deadline vs. bid-validity end) is an assumption.
21. Municipalities (753) are not mapped; only district/province.
22. `parse_bs_date` cannot tell an AD date from a BS date; callers must know it is BS.

New (Prompt 1):
12. **Local dev hardware (8GB RAM / 4GB VRAM) can't comfortably run the pinned 7B chat model (Qwen2.5-7B-Instruct)** via Docker's `ollama` service — a 4-bit-quantized 7B model is ~4.7GB, tight alongside Windows + Docker Desktop + the other three containers. Verified the pull mechanism with the much lighter `bge-m3` embedding model instead; did not attempt the full 7B pull. **Team decision needed before Prompt 2 starts calling the LLM for real.** Options, roughly in order of preference:
   - Bump Docker Desktop's memory limit (Settings → Resources) on whichever machine has more RAM headroom.
   - Run Ollama natively on Windows (not inside Docker) for full system RAM + GPU access via CUDA, pointing `LLM_BASE_URL` at `http://host.docker.internal:11434`.
   - Point `LLM_BASE_URL`/`LLM_MODEL` at a hosted open-weight inference provider (e.g. one serving Qwen2.5/Llama, not a proprietary model) for day-to-day dev — CLAUDE.md hard rule 1 explicitly allows this as a config change.
   - Reserve local Docker + the 7B model for final demo rehearsal on whichever teammate's machine has the most RAM/VRAM.

New (Prompt 2):
13. **The real-Ollama smoke test has never run.** No Ollama was reachable on this machine (blocked on issue 12). Run `uv run pytest -m ollama` once a model is available (a small model such as `qwen2.5:1.5b-instruct` is fine for this plumbing check). It is still unverified that Ollama's grammar accepts our schemas' `pattern`/`format` keywords.
14. **`bun run test` fails on this machine, before and independent of this prompt's change.** There is no Node.js on PATH, so vitest's worker runs under Bun and jsdom throws `addEventListener ... not a valid instance of EventTarget`. Prompt 1 verified it elsewhere. Options: switch the vitest environment to `happy-dom`, or document Node as a test-runtime requirement. Needs a team call (CLAUDE.md says Bun only).
15. `bunx tsc --noEmit` reports `Cannot find name 'LayoutProps'` in `app/layout.tsx`. That is a Next.js-generated global that only exists after `next build`/`next typegen`, so it is not a real error. `bun run build` remains the type-check of record.

New (Prompt 4):
23. **Seed with real embeddings not run.** No Ollama on this machine, so run `uv run python -m scripts.seed_demo` once `bge-m3` is pulled (issue 12/13).
24. **Docker image not rebuilt/verified** after the Dockerfile change (migrations on start, `--no-dev`). There is no Docker here. Check with `docker compose up --build`. The seed runs from the host, because `data/` is outside the api build context.
25. **`bun run build` fails on this machine at "Collecting page data"** (`Expected CommonJS module to have a function wrapper ... bug in Bun`). It is identical on clean HEAD, and TypeScript type-checking passes. Same root cause as issue 14 (no Node on PATH).
26. Duplicate uploads (same `sha256`) are allowed. Add a dedupe or replace option if the UI needs it. There is no re-ingest or delete endpoint yet (the seed re-ingests by deleting and recreating).
27. No Preeti-to-Unicode conversion; such PDFs only get a warning (NEPAL_CONTEXT section 9).
28. Starlette warns that `TestClient` with `httpx` is deprecated (`httpx2`). Not ours to fix yet.

Other:
- The spec's AI-disclosure table (§15.1) is garbled in the PDF text extraction. Function names will be finalised from real code.

## Next prompt
Prompt 5: Scout + tenders. Wire the DB-backed `run_recorder` (`db.make_run_recorder`, done) into the orchestrator. Build the Scout agent (`LLMClient.chat(stage=SCOUT, schema=TenderRecord)`, then `deadline_from_raw` / `parse_npr` overwrite code-owned fields, then fill the denormalised `tenders` columns) and add `TenderCriteria` extraction. Write the seed tender dataset (30-40, data/tenders/) with a loader and `POST /tenders/scrape`. Write the `documents` -> `DocumentMeta` loader so `nepal.rules.evaluate_rules` can run against the demo company (expect NP-TAX-CLEARANCE to fail on the expired FY 2081/82 clearance). Resolve open issues 12/13 first if possible, then run the seed with real embeddings (issue 23).
