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

### Prompt 5a: seed tenders, live scraper, POST /tenders/scrape (2026-10-19) ✅
- **Seed dataset:** `data/seed_tenders/` has 37 **synthetic** notices (`NNN_slug.txt`, each starting with a `[SYNTHETIC SEED NOTICE ...]` banner) plus `manifest.json` (`"synthetic": true`, FICTIONAL comment). Buyers are real public bodies for realism; works, refs, amounts, dates, phones and bank accounts are invented. Coverage: works 22 / goods 8 / consulting 4 / non-consulting 3; NCB 19, sealed quotation 10, ICB 3, EOI 2, RFP 2, prequalification 1; buyers local 25 / province 6 / federal 6, across all 7 provinces (Gandaki 24, since the demo SME is there); en / ne / mixed; BS-only, AD-only, both, and none; Rs., NPR, रु., lakh, crore, million, "in thousands" tables, Devanagari numerals; bid security as an amount and as a percentage only; JV allowed, barred and silent; domestic preference.
  - Demo roles: **001 strong match** (Bhanu Municipality, Tanahun, road gravelling, 1.49 cr; class D+, turnover ≥1.5 cr, experience ≥60 lakh, JV allowed). **002 hard fail** (Gandaki Province Seti River training, 18.5 cr; class A/B, avg turnover ≥25 cr vs the company's ~5 cr, 9 cr single contract, JV barred). **003 irrelevant** (DoHS ICU-ventilator ICB). Messy: 004 (no computable deadline), 005 (cost "in thousands" vs "about fifty lakh"), 006 (PDF copy-paste artifacts), 007 (corrigendum), 033 (two deadlines + compound amount), 034 (mis-grouped figure contradicting the words), 037 (cancellation notice). 008 has a passed deadline. 015/016/019/027/029 are further good matches.
  - Each `expected` block is hand-labelled ground truth for Scout golden-set checks: deadline BS/AD, cost, bid security, JV, plus verbatim `*_quote` fields. Tests check every quote is verbatim, parses with `parse_npr` / `parse_bs_date` to the labelled value, and that BS/AD pairs agree via `bs_to_ad`.
- **Source check (robots/ToS), recorded in NEPAL_CONTEXT §6:** bolpatra 403, NEA WAF page, PPMO and Pokhara connection resets, so none of them are used. **kankaimun.gov.np** (MoFAGA Drupal site): robots allows the notice board, notice pages and attachments, with `Crawl-delay: 10`; no terms page found; no login. Chosen as the one live source.
- **Scraper (`api/ingest/scraper.py`):** `PoliteFetcher` (httpx, honest UA + optional `SCRAPER_CONTACT`, robots read first and checked per URL, ≥10 s between requests or the robots delay if larger, GET only, same host only, no redirects followed, 401/403/429 stops the run without retry, unreadable robots means nothing is fetched, 10 MB cap, raw disk cache in `api/.cache/scraper/` with the listing re-read after 6 h and notice pages and attachments never refetched). `parse_listing` / `parse_notice` (BeautifulSoup, stdlib `html.parser`), a Nepali+English procurement keyword filter (the board mixes exam, meeting and holiday notices), and attachment text via `parse_pdf` / `parse_docx`. **Scanned PDFs are skipped and reported** (no OCR). Output is raw text only (title, source URL, published timestamp, body, attachment text).
  - **What it does / does not do:** it reads the board and pulls text from HTML bodies and text-layer PDF/DOCX attachments. It does **not** OCR, log in, follow links off-host, retry refusals, or extract fields. **Live run on 2026-10-19:** 6 requests, ≥10 s apart, not blocked. **Both current tender notices were scanned PDFs, so 0 usable notices.** The live source produces little today. Seed data is the demo source, and the scraper is not a dependency.
- **Upsert (`api/ingest/notices.py`):** `RawNotice` and `upsert_notices` (by `source_url`). New rows get status `new` with raw text only. Identical text is left alone, keeping status and progress. Changed text is reset to `new`, derived columns are cleared and its `matches` / `compliance_items` rows are deleted (proposals are kept). `ingest/seed_tenders.py` refuses a manifest without `synthetic: true`.
- **Endpoint:** `POST /tenders/scrape` takes an optional `ScrapeRequest` (`source`: `seed` (default) | `kankai`, `max_pages` ≤3, `max_notices` ≤10) and returns `ScrapeReport` (created / updated / unchanged / tender_ids / skipped[url, reason] / blocked). A missing seed dir returns 503. New enum `TenderSource` (not a DB column, so no migration). Settings: `SEED_TENDERS_DIR`, `SCRAPER_USER_AGENT`, `SCRAPER_CONTACT`, `SCRAPER_MIN_DELAY_S`, `SCRAPER_CACHE_DIR`. docker-compose mounts `./data/seed_tenders` read-only at `/data/seed_tenders`. `web/lib/api/types.ts` regenerated (`bun run gen:api`).
- **Fixtures:** `api/tests/fixtures/scraper/`: a trimmed copy of the real listing (10 rows + pager; footer with an officer's contact removed), a trimmed real notice page (scanned-PDF attachment), a **constructed** notice page with a body (same markup, synthetic text), and the real robots.txt (abridged).
- Dep added: `beautifulsoup4` (+ `soupsieve`). Audited: pure-Python HTML parser, MIT, no network or model use.
- **Tests:** `uv run pytest -q` gives **359 passed, 1 deselected** (was 290): `test_seed_tenders.py` (45: labelling, coverage, demo roles vs `profile.json`, ground truth per notice), `test_scraper.py` (17: parsing real markup, keyword filter, politeness with a fake clock, cache reuse, robots disallow / 403 / 5xx / 404, 429 stops without retry, off-host attachment never fetched), and `test_tenders_scrape_api.py` (7, Postgres: seed load offline with a transport that fails on any HTTP, idempotent reload keeps progress, changed text resets, 503, 422, live source via the mock site, blocked reported rather than raised).

### Prompt 5b: Scout agent (2026-10-19) ✅ (offline). Real-model score NOT run
- Read spec §8.1 (agent contracts) and §8.2 (design rules) this session, from the PDF.
- **LLM half:** new `schemas/scout.py::TenderExtraction` is what the LLM fills (instead of `TenderRecord`). Every value is a `Grounded {value, quote}` pair of verbatim strings: deadline, cost, bid security and its validity, bid validity, fee, performance security, turnover and similar-contract minimums, location, title, buyer, reference. Required docs are `{name, mandatory, source_quote}` and requirements use `Requirement`. The enum judgments (type, method, buyer level, evaluation, JV, domestic preference) each come with a `*_quote`. The prompt (`agents/scout.py::SYSTEM_PROMPT`) says "copy, do not convert": keep Devanagari digits and units, copy the submission deadline (not publication/opening; the new date in a corrigendum), give one entry per document, and includes a Nepali term glossary. Temperature 0 via `STAGE_TEMPERATURE`.
- **Code half (`postprocess`, pure):**
  - `Grounder` checks every raw string and quote is in the notice. It tolerates only whitespace, case, digit script and quote style.
  - `nepal.parse_deadline` produces the AD datetime + BS ISO. `parse_npr` produces cost, fee and turnover. `parse_percent` / `parse_days` handle security and validity; a validity printed as a date becomes days after the deadline.
  - `normalize_location` fills district/province (location, then buyer address, then buyer). `classify_document` + `find_fiscal_years` give DocType and FY.
  - The bid-security due amount comes from `calc_bid_security`. `TenderCriteria` (turnover min + look-back years when one count is stated, similar-contract min) now lives on the record (issue 18). `language` is computed.
  - If a raw value is not verbatim or does not parse, the value is null, the raw string is kept, a `ReviewFlag` is added and `needs_review` is set. `sources[]` stores value, raw, quote and char span for the UI.
- **Nepal layer additions:**
  - `parse_deadline` (BS+AD in one string with a cross-check, Devanagari/danda, BS + English month names, `HH:MM`/`hours`/`PM`/`noon`/`बजे`/`दिनको`; reports issues instead of guessing).
  - `parse_npr` is now strict on digit grouping and sums descending-unit compounds. Added `parse_percent`, `parse_days`, `has_thousands_marker`.
  - New `nepal/documents.py`.
  - Together these close open issue 30.
- **Schema moves:** `TenderCriteria` and `SecurityCalc` moved to `schemas/tender.py` (re-exported from `nepal.rules` / `nepal`). `TenderRecord` gained the code-owned `criteria`, `bid_security_due`, `sources`, `review_flags` and `needs_review`, all stored in `record_json`, so no migration. `evaluate_rules` defaults `criteria` to `tender.criteria`. `deadline_ad` is now always set by code when the deadline is confirmed.
- **DB write:** `run_scout(session, client, tender)` / `scout_new_tenders` fill `record_json` + the denormalised columns and set `extracted`, or `failed` on `LLMError` / empty text. The agent_runs row comes from the client callback (`db.make_run_recorder`) and holds the raw LLM extraction.
- **CLI:** `cd api && uv run python -m api.agents.scout --seed [--only ..] [--json ..] [--db]` prints a field table (deadline BS/AD, cost, bid security, language, district, doc types, flags).
- **Golden set:** `data/golden/scout_expected.json` has 15 ids. 5 are hand-labelled (001 mixed, 002 EN crore, 003 AD-only ICB, 005 "in thousands" ambiguity, 012 all-Nepali SQ): deadline BS + AD datetime, cost, required doc types. 10 are `todo`. The labelling rules are in the file. **Scorer:** `scripts/score_scout.py` reports field-level accuracy for deadline (BS, AD to the minute), budget, and docs (P/R/F1 + exact-set). A null label is correct only for null output, and a failed run is wrong on every field. `--manifest` also scores deadline/cost on all 37 seeds; `--predictions` scores saved CLI output.
- `LLM_NUM_CTX` (default 8192) is passed as Ollama `num_ctx`. The default 2048/4096 window would silently drop the system prompt on long Devanagari notices. Added to `.env.example`.
- `web/lib/api/types.ts` regenerated (`bun run gen:api`; TenderRecord's new fields).
- **Tests:** `uv run pytest -q` gives **427 passed, 2 deselected** (was 359); **430** after the CLI module-path follow-up.
  - `test_nepal_scout_parsers.py` (43): deadline formats; never-guess cases; every seed manifest deadline quote parses to its label; compound / mis-grouped amounts; percent/days; doc classification; FY.
  - `test_scout.py` (25): grounder; language vs all 37 manifest labels; a full 001 record from a hand-written ideal extraction; every source span points at its quote; a converted amount or deadline is not trusted; BS/AD mismatch; corrigendum; 034 garbled grouping; 005 thousands table; 033 percent security + compound cost; ambiguous district; hallucinated text flagged; fake-LLM call (schema, temperature 0, num_ctx, one agent_runs row, strict int rejection → retry → `LLMOutputError`); CLI table; Postgres `run_scout` (row columns, extracted/failed, agent_runs rows, no re-run); golden file vs manifest; scorer arithmetic.
  - New `-m ollama` smoke test runs Scout on seed 001.
- **Scorer on the real model: NOT run.** No Ollama on this machine (`curl localhost:11434` refused; issues 12/13). The CLI was run and fails cleanly: both notices show `FAILED /api/chat failed: connection refused`, exit 1. **No accuracy numbers exist yet.** For reference, an ideal (hand-written) extraction of 001 scores 100% on all fields (`test_scorer_on_ideal_extraction_of_001_is_perfect`), so that is the ceiling the code half allows, not a model result.

### Prompt 6: Matching agent, ranked GET /tenders (2026-10-19) ✅ (offline). Real-model metric NOT run
- Read spec §8.1, §10.3 and §10.4 this session, from the PDF.
- **`agents/matching.py::score_tender(record, company, chunks, client=, settings=, now=)`**:
  - **Deterministic signals** (`deterministic_signals`, 100 points): procurement type vs the new `CompanyProfile.procurement_types` (30), district/province served (30), estimated cost vs `MATCH_MAX_COST_TO_TURNOVER` x average turnover of the last 3 FYs (25), deadline in NPT incl. a tight-deadline penalty (15). A failed check is a **hard skip**. A missing value (no district, cost or confirmed deadline) loses points and never skips.
  - **Model signal** (`assess`): `MatchAssessment` at temperature 0. The prompt asks for scope relevance only, shows top-k KB chunks as `[chunk N]`, and withholds deadline, cost and location (a test enforces this). It is **not called** when a rule already hard-skips (`MATCH_LLM_ON_HARD_SKIP=false`), which saves a 7B call per obvious skip.
  - **`combine` (code decides):** score = 0.6 x semantic + 0.4 x deterministic. A hard skip caps the score at threshold-1, so skipped tenders always rank below pursued ones. pursue iff score >= `MATCH_THRESHOLD` (60) and no hard skip. Every reason is prefixed `[deterministic]` or `[model]`. `MatchResult` gained `deterministic_score`, `semantic_score`, `llm_weight`, `skip_reasons`, `signals[]` (`MatchSignal`, `SignalSource`) and `chunk_ids`.
- **DB:** `run_matching` retrieves chunks (`db.search.retrieve`, `MATCH_TOP_K`=5; skipped on a hard skip), replaces the tender's single `matches` row (`reasons` JSONB = full `MatchResult` dump), and sets `matched` / `skipped`. LLM or embedding failure sets `failed` and drops the match. A code-only run writes its own agent_runs row (`model="deterministic"`, hard rule 9); an embedding failure writes a failed row. Matchable from `extracted/matched/skipped/failed` (with a record). `match_extracted_tenders` batches. `pipeline/orchestrator.py::analyze_tender` runs Compliance only when the tender is `matched` (the hook is None until Compliance lands).
- **API:** `GET /tenders` is ranked (score desc, deadline asc, unscored last), with filters procurement_type, method, province, district (EN/NE normalised), buyer_level, min_score, deadline_within_days, language, plus decision, status and limit/offset. Each row is a `TenderListItem` with `DeadlineView` (AD in NPT, BS ISO, `"5 Mangsir 2083"`, Devanagari, `days_left`, `passed`). `GET /tenders/{id}` returns `TenderDetail` (+ `deadline_view`). `POST /tenders/{id}/analyze` runs Matching (409 if not matchable / no company). `deps.get_now` is the injectable NPT clock. `web/lib/api/types.ts` regenerated (`bun run gen:api`).
- **Demo data:** `profile.json` gained `"procurement_types": ["works"]`. `data/golden/match_relevance.json` hand-labels all 37 seeds: 6 `core` (the manifest's strong/good matches 001, 015, 016, 019, 027, 029), 5 more `relevant` (in-scope messy works 004, 005, 006, 033, 034), and 26 not relevant, each with a reason.
- **Metric script:** `scripts/score_matching.py`. Ranks like the API at the labels' fixed clock (2026-10-19 12:00 NPT). Default: "oracle" records from the manifest labels + deterministic signals only. `--llm` adds the real model; `--records` uses saved Scout output.
- **Measured (deterministic only, oracle records, no model):**
  - top 3 = 027, 033, 006. **relevant precision@3 = 1.0**, **core precision@3 = 0.33** (1/3).
  - core ranks: 027 -> 1, 001 -> 4, 019 -> 5, 029 -> 6, 015 -> 7, 016 -> 8.
  - relevant pursued 11/11 = **1.0**. Irrelevant skipped 24/26 = **0.92**: the false pursues are 007 (corrigendum, no scope) and 037 (cancellation); only the model can tell those. Pursue precision 11/13 = 0.85.
  - All in-scope works tie at deterministic 100, and ties break by soonest deadline. So **ordering within the relevant set is entirely the model's job**, and core@3 = 0.33 is the code-only floor, not a model result. The other skips are all right: 002 (3.68x turnover), 032 (6.36x), 008 (deadline passed 2026-10-14), 003/013/014/022/023/024/030/035 (goods), consulting/services, and 017/018/020/028/036/021 (outside the districts served).
- **Tests:** `uv run pytest -q` gives **502 passed, 3 deselected** (was 430).
  - `test_matching.py` (42): each pre-filter incl. the NPT deadline boundary (12:00 NPT = 06:15 UTC); budget bands and the configurable cap; combine weights, caps, inclusive threshold and reason prefixes; the fake-LLM call at temp 0 with the schema; no model call on a hard skip; string score -> retry -> `LLMOutputError`; the prompt withholds code-owned facts; DB persist, re-run replaces, failed on a model or embed error, refused statuses, no company; a skipped tender never reaches the Compliance hook; the offline metric; labels vs manifest roles.
  - `test_tenders_list_api.py` (30): ranking order; AD+BS+days_left; every filter incl. a Nepali district and combinations; 422s; pagination ranks; detail; analyze end to end; profile round-trip.
  - `test_health` now checks the still-stubbed proposal route for 501. New `-m ollama` smoke test: the real model rates 001 above 003.
- **Not run:** `score_matching --llm` and the new smoke test. There is still no Ollama on this machine (`curl localhost:11434` refused).

### Prompt 7: Compliance agent, override, analyze = Matching + Compliance (2026-10-19) ✅ (offline). Real-model metric NOT run
- Read spec §8.1, §8.2 and §17 this session, from the PDF.
- **`agents/compliance.py::check_requirements(tender, company, documents, client=, retrieve_fn=, now=)`**, in two layers:
  - **Layer 1 (rules):** `nepal.rules.evaluate_rules`. Changes to the Prompt 3 engine:
    - every outcome now carries `evidence_document_ids` and a plain-language `action_needed` (null on pass);
    - a pass needs a readable KB document (chunk id) or a `tender.*` field. A profile entry alone is no longer evidence, so NP-LICENCE-RENEWAL and NP-JV need the licence copy / JV agreement;
    - the self-declaration and power of attorney moved from NP-REG-DOCS to the new **NP-BID-FORMS** (signed per bid, never a fail);
    - new **NP-DOC-VALIDITY** (dated eligibility documents lapsing between the deadline and deadline + bid validity: unclear + "renew before" action, soft, `[VERIFY]`);
    - new **NP-OTHER-DOCS** (mandatory notice documents no rule checked; runs last; never a fail);
    - the NP-TAX-CLEARANCE message lists what is on file with expiry dates;
    - `DOC_RULES` maps doc types to rules. 14 rules in total.
  - **Layer 2 (model):** `covering_rules` / `needs_model` route each `TenderRecord.requirements` entry deterministically: doc types via `classify_document`, plus turnover / experience / bid-security wording. A rule that did not fire for the tender covers nothing. Residual aspects (licence class, personnel, equipment, liquid assets, ...) go to the model even when a rule covers the rest. Each such requirement gets its own top-k retrieval (`COMPLIANCE_TOP_K`=4) and one `ComplianceAssessment` call at temperature 0. The prompt says when to answer unclear, ranks licence classes (A > B > C > D, क/ख/ग/घ), and lists what code already checked.
  - **`ground()`**: cited chunk ids must be among the excerpts shown, and the quote must be in a cited chunk (`agents.scout.Grounder` tolerance). Otherwise a pass or fail becomes `unclear`, and the reason is written into the explanation. Severity is code's: mandatory -> hard.
- **Schemas:** `ComplianceAssessment` is now ONE requirement (`status`, `evidence_chunk_ids`, `evidence_quote`, `explanation`; no severity, rule_id or requirement). A pass or fail without a chunk id is invalid output, so it is retried and then fails the stage. `ComplianceFinding` was removed. `ComplianceItem` gained `source` (new enum `ItemSource`), `evidence_document_ids`, `evidence_ref`, `action_needed` and `requirement_index`, and its validator now requires a pass to have a chunk id, a document id, or a rule citing `tender.*`. New `ComplianceOverride`, `ComplianceOverrideRequest` and `ComplianceView` (items, blocked, hard_failures, counts, override, proposal_allowed). `TenderDetail.compliance` is now a `ComplianceView`, and `TenderListItem` gained `hard_failures`.
- **DB (migration `0002`):** `compliance_items` + `source` (CHECK), `evidence_chunk_ids` / `evidence_document_ids` (INT[]), `evidence_ref`, `evidence_quote`, `action_needed`, `requirement_index`; new table `compliance_overrides` (tender_id, overridden_by, reason, hard_failures JSONB of `ComplianceItem.key`, created_at). `upsert_notices` drops overrides too when the text changes.
- **`run_compliance`:**
  - runs from matched/checked/blocked;
  - loads `DocumentMeta` from `documents` (`load_document_meta`: chunk id = first chunk of a `ready` document; closes the loader half of issue 19);
  - replaces `compliance_items`, writes one `deterministic` agent_runs row for the rules layer (each model call writes its own through the client), and sets `checked` / `blocked`;
  - sets `failed` on an LLM error. An embedding failure (`RetrievalError`) writes its own failed row.
  - **Override:** `override_block` stores who, why, when and which failures, and sets `checked`. It stays active only while every current hard failure is among those accepted, so a re-check that finds a new hard failure blocks again. `proposal_allowed` is the Proposal gate.
- **API:**
  - `POST /tenders/{id}/analyze` = Matching (new `rematch=True`, which also accepts checked/blocked) then Compliance. A tender Matching no longer pursues loses its stale items.
  - `GET /tenders/{id}` includes the compliance section; `GET /tenders` rows include `hard_failures`.
  - new `POST /tenders/{id}/compliance/override` (422 / 404 / 409);
  - `POST /tenders/{id}/proposal` returns 409 while blocked (or not checked), and 501 once the gate passes (the stage is not built yet).
  - `web/lib/api/types.ts` regenerated (`bun run gen:api`); `bunx tsc --noEmit` is clean apart from the known LayoutProps issue.
- **Demo data:** added `data/demo_company/06_construction_licence.txt` (FICTIONAL, class C, DEMO-C-0421, renewed for FY 2083/84, valid to 2084-03-32 BS). Without it, NP-REG-DOCS hard-failed every tender (no licence document in the KB). The expired FY 2081/82 tax clearance is kept as the demo beat (**issue 29 decided: option (a)**).
- **Golden set:** `data/golden/compliance_requirements.json` hand-labels **54 mandatory requirements** across 7 pursued seeds (001, 002, 015, 016, 019, 027, 029). Each label has a verbatim quote (tested), a plain-English text, the verdict for the demo company from its KB, hard yes/no, and a rule id or keywords. Oracle Scout fields (required docs, criteria, bid security, bid validity) are labelled too. There are 11 must-fail labels: tax clearance x7, and for 002 also licence class, turnover, experience and equipment.
- **Metric script:** `scripts/score_compliance.py` reports recall (requirements covered), **hard-fail recall** (the worst error), status accuracy, false hard fails and blocked accuracy. The demo KB is parsed and chunked like ingest into memory. `--llm` adds the real model with in-memory top-k retrieval; `--records` uses Scout output.
- **Measured (oracle records, rules only, no model; 2026-10-19 12:00 NPT):**
  - **recall = 1.0** (54/54 requirements covered by some item);
  - **hard-fail recall = 0.818** (9/11). Missed: `002:licence_class` and `002:key_equipment`. Both are model-layer requirements, which are unclear without a model.
  - status accuracy 0.667 (36/54). The gaps are conservative unclears: turnover (look-back years not extracted, no audit reports), experience (certificates not classified `similar`), and the model-layer passes (licence class, personnel, equipment);
  - **false hard fails 0**; blocked accuracy 1.0 (7/7 blocked, all on NP-TAX-CLEARANCE).
  - The model layer can only add hard fails, so 0.818 is the floor; 1.0 needs the model to fail 002's class A/B and its batching plant.
- **Tests:** `uv run pytest -q` gives **552 passed, 4 deselected** (was 502).
  - `test_compliance.py` (42): routing; the prompt; **the demo expired-document case is a hard fail that blocks**, with document id and action; a fresh clearance unblocks; 002 fails on turnover/experience with JV barred; one call per uncovered requirement (schema, temperature 0, one agent_runs row each); **unclear-never-pass** (unknown chunk, quote not in chunk, no quote, fail without evidence, schema rejects a chunk-less pass and retries, offline, every pass across all golden tenders); a mandatory model fail is hard, an optional one soft; the DB loader; persistence and round trip; re-run replaces; **the override path** (stored who/why/when/keys, gate opens, survives a same-failure re-check, a new failure blocks again, refused unless blocked); failed on model or embedding error; refused statuses; analyze from blocked; stale items dropped; golden quotes verbatim; scorer arithmetic; offline metric floor; CLI.
  - `test_compliance_api.py` (3): analyze -> blocked with the detail section and list `hard_failures`; proposal 409 -> override 422/200 -> proposal 501 -> second override 409; 404s.
  - `test_nepal_rules.py` +6 (expired clearance, bid-validity lapse, other docs, an action on every non-pass, profile is not evidence, bid forms).
  - New `-m ollama` smoke test for Compliance on 001 (not run).
- **Not run:** `score_compliance --llm` and the smoke test. There is still no Ollama on this machine (`curl localhost:11434` refused).

### Prompt 8: orchestrator state machine, pipeline runs, background analyze, pre-cache (2026-10-19) ✅ (offline)
- Read spec §10.3, §10.5 and §12 (Day 6) this session, from the PDF.
- **`pipeline/orchestrator.py`** (rewritten):
  - `TRANSITIONS` is the legal edge table. `HUMAN_TRANSITIONS` = override (blocked→checked) and approval (reviewed→approved).
  - `STEPS`: Scout new→extracted, Matching extracted→matched|skipped, Compliance matched→checked|blocked, Proposal checked→drafted, Review drafted→reviewed.
  - Runners default to `run_scout` / `run_matching(rematch=True)` (+ dropping stale compliance items when not pursued) / `run_compliance`. Proposal and Review are `None` until those agents exist; they are tested with injected runners.
  - **Resume:** `resume_status` derives a failed tender's last good state from stored data (no record → new; no match row → extracted; pursued match → matched), because every failing stage drops its own partial output. This works whatever started the stage (API or CLI).
  - **Planning:** `plan_run` continues forward. It re-runs from Matching for skipped/blocked/checked tenders or when the target is already reached (re-analysis after uploading a document). `from_stage` rewinds. It refuses with ValueError → 409: drafted+ without `from_stage`, target `approved` (human), stages with no runner, no company, or a `from_stage` the tender has not reached.
  - **Execution:** `start_run` stores a `queued` `pipeline_runs` row. `execute_run` is the background task:
    - Stage bookkeeping (status, timestamps, `duration_ms`, heartbeat) is written in its own short sessions, so it never commits half-done tender work.
    - After each runner, the tender's status must be a legal edge from the step's start, or the run fails ("illegal transition").
    - A raising stage is rolled back, the tender set `failed`, and an `agent_runs` row written (`model="orchestrator"`).
    - The run ends `succeeded` / `stopped` (branch) / `failed`. Untaken stages become `not_run`, and the run is never left `running` by a live worker.
  - `run_pipeline` is the synchronous wrapper (scripts, tests). The old `analyze_tender` is gone.
- **Linking agent_runs:** `db.runs.current_pipeline_run` (a ContextVar) plus a `before_insert` hook stamp `pipeline_run_id` on every agent_runs row written during a run. That includes the agents' own code-only rows, with no agent changes. The recorder bumps the run's heartbeat on every model call.
- **Stuck runs:** `reap_stale_runs` runs at startup (FastAPI lifespan; reaps every queued/running run, since background tasks die with the process) and on every `GET /runs*` (heartbeat older than `PIPELINE_STALE_AFTER_S`, default 600). Tender statuses are only ever committed as resting values, so a reaped run's tender sits at its last good state. The lifespan logs and carries on if the DB is unreachable.
- **DB (migration `0003`):**
  - `pipeline_runs`: target, status with CHECK `RunStatus`, start/resumed_from/end status, `stages` JSONB of `StageRun`, error, created/started/finished/heartbeat timestamps.
  - **Partial unique index** `uq_pipeline_runs_active_tender` allows one queued/running run per tender.
  - `agent_runs` gains `pipeline_run_id` (FK SET NULL) and `cached`.
- **API:**
  - `POST /tenders/{id}/analyze` now returns **202 + `PipelineRunView`** and runs in a FastAPI `BackgroundTasks` (no queue). It takes an optional body `AnalyzeRequest {target (default checked), from_stage}`. A `new` tender is accepted (Scout runs first).
  - New `GET /runs` (newest first; filters `tender_id`, `status`, `limit`/`offset`).
  - `GET /runs/{id}` returns `PipelineRunDetail`: stages with from/to status, timestamps and `duration_ms`, plus the run's agent_runs rows.
  - New schemas: `RunStatus`, `StageStatus`, `StageRun`, `AnalyzeRequest`, `PipelineRunView`, `PipelineRunDetail`. `AgentRun` gains `pipeline_run_id` and `cached`. `web/lib/api/types.ts` regenerated; `bunx tsc --noEmit` is clean.
- **Failure handling (spec §10.5):**
  - Per-call timeout (`LLM_TIMEOUT_S`) and one schema retry stay in `LLMClient`.
  - A failed stage's run carries the error of its failed agent_runs row (e.g. `compliance: attempt 2: ... validation error`).
- **Pre-cache:**
  - `pipeline.llm.ReplayCache` is a JSON file of validated chat outputs keyed by the client's request hash (model + stage + messages + schema + temperature), plus embeddings keyed by (model, text).
  - A hit is re-validated strictly and still writes its agent_runs row, marked `cached`. A stale or invalid entry, or a miss, goes to the live model.
  - `LLM_REPLAY_CACHE` turns it on for every client (read-only). docker-compose points it at `data/demo_cache/llm_cache.json` (mounted read-only); nothing happens until the file exists.
  - `scripts/precache_demo.py` runs Scout→Matching→Compliance (`from_stage=scout`) on seeds 001/002/003 with a recording client (`--seed-company` also caches the KB embeddings). It prints a status table.
  - `--check` replays with a transport that refuses all HTTP and exits 1 on any miss.
- **Tests:** `uv run pytest -q` gives **603 passed, 4 deselected** (was 552).
  - `test_orchestrator.py` (38):
    - the transition table (+10 illegal pairs);
    - new→reviewed through all five stages, with one agent_runs row per transition linked to the run;
    - each single transition;
    - the skipped branch (Compliance never called);
    - the blocked branch (Proposal never called);
    - **real agents on raw notice 001: new→extracted→matched→blocked**;
    - failure at Scout/Matching/Compliance;
    - real Scout invalid twice (exactly one retry);
    - a crashing stage (rolled back, tender failed, orchestrator row);
    - illegal transitions;
    - `resume_status` derivation;
    - **resume after a Compliance failure skips Matching**, and resume after a Scout failure;
    - re-analysis planning, `from_stage` rewind and refusals, no company;
    - one active run (incl. the DB index);
    - the worker ignores non-queued runs;
    - the reaper (stale vs fresh, startup).
  - `test_runs_api.py` (5): 202 → poll, failed then resumed via the API, list order/filters/paging/422, 404/409, polling reaps a dead run.
  - `test_llm.py` +6 (record/replay with no HTTP, miss, invalid entry ignored, keyed by model, embeddings fetch only missing texts, setting pickup).
  - `test_precache.py` (2): record then `--check` offline with every model row `cached`, and a removed entry makes `--check` fail.
  - Updated: the analyze tests in `test_tenders_list_api.py`, `test_compliance_api.py`, `test_compliance.py` and `test_matching.py` (202 + poll, `run_pipeline`; `new` is no longer 409).
- **Not run:** a real recording of `data/demo_cache/llm_cache.json` (no Ollama here), and Docker (no Docker here).

### Frontend prompt: app shell, dashboard, company page (2026-10-19) ✅ (mock mode verified in the dev server; not run against a live API)
- Read spec §9 this session (pages, server components for lists, typed client, 2 s polling, shadcn/ui).
- **App shell** (`app/layout.tsx`): header nav (Dashboard, Company, Runs), language toggle EN / नेपाली and calendar toggle BS / AD (`components/app-shell/`), both in localStorage (`tenderly.lang`, `tenderly.calendar`; defaults en + BS). Fonts: Geist for Latin + **Noto Sans Devanagari** (`next/font/google`, subsets devanagari+latin) via the `--font-sans` stack in `globals.css`; `:lang(ne)` gets taller line height. `<html lang>` follows the toggle. Amber banner when mocks are on.
- **i18n** (`lib/i18n/dict.ts`): one flat dictionary per language, `translate()` with `{placeholders}` (numbers become Devanagari digits in Nepali) and `enumLabel()` for every API enum. Labels only; tender data is shown as the API returns it. `lib/prefs.tsx` holds `PreferencesProvider` (useSyncExternalStore, so SSR/hydration use defaults with no mismatch) and the `<T k=…/>` / `<EnumText/>` leaves that server components use.
- **Utilities:** `lib/format.ts` (`groupLakh` 1,48,75,000, `formatNpr`, `formatNprShort` "Rs. 1.49 crore" / "रु. १.४९ करोड"), `lib/nepal/calendar.ts` (BS↔AD, `parseBsIso` with Devanagari digits, `formatBs` = the API's `bs_long`/`bs_ne` forms, `formatAd`, `formatDate`), `lib/deadline.ts` (NPT calendar days identical to `DeadlineView.days_left`, `countdown` with urgency ok/soon ≤7/urgent ≤3/today/passed, hours+minutes in the last 24 h, `countdownText` en/ne), `lib/reasons.ts` (parses `[deterministic]`/`[model]`/`SKIP:` prefixes; preview leads with skip, then model reasons), `lib/clock.ts` (`useNow`, 30 s tick, null during SSR so the API's `days_left` is shown first).
- **BS calendar = backend export.** `api/scripts/export_bs_calendar.py` writes `web/lib/nepal/bs-calendar.json` (BS 2000–2099 month lengths + 1 Baisakh AD, from `nepal.dates`/`nepali-datetime`); `api/tests/test_bs_calendar_export.py` fails on drift. See Decisions.
- **Typed API client:** `lib/api/client.ts` (`getApiClient()`; server uses `API_URL`, browser `NEXT_PUBLIC_API_URL`), `lib/api/tenderly.ts` (listTenders, scrapeTenders, getCompany (404 → null), saveCompany, listDocuments, uploadDocument (multipart via `bodySerializer`), `parseTenderFilters` for URL → GET /tenders query, `errorMessage` for FastAPI `detail`), `lib/api/enums.ts` (runtime enum lists with a compile-time exhaustiveness check against the generated types).
- **Mock fallback:** `NEXT_PUBLIC_USE_MOCKS=1` routes every call to `lib/mock/api.ts` (10 tenders modelled on the synthetic seeds incl. blocked 001, over-capacity 002, goods 003, passed 008, unextracted 033, needs-review 034; the demo profile; 4 KB docs incl. the expired FY 2081/82 clearance and a `needs_ocr` scan). Deadlines are relative to now and converted with the same calendar code. Filters are emulated (incl. Nepali district names); uploads go `processing` → `ready` after 3 s. State is per tab (client) / per process (server).
- **`/` dashboard** (server component, `connection()` + Suspense because `cacheComponents` is on): ranked rows (`components/tenders/tender-row.tsx`) with rank, score bar + decision, status badge (colour per status), title (with `lang="ne"` for Nepali notices), buyer, buyer-level / type / method / language badges, province / district, cost in lakh/crore (full grouping on hover), hard-failure and needs-review badges, 2-reason preview with rule/model tags, deadline in both calendars (preferred first, NPT time) + live countdown. Filter bar (`tender-filters.tsx`) drives the URL: all 10 GET /tenders filters (type, method, buyer level, province, language, decision, status as selects; district, min score, deadline-within as inputs). "Load tenders" posts `{"source": "seed"}` to `/tenders/scrape`, shows created/updated/unchanged and `router.refresh()`es. Empty and API-unreachable states.
- **`/company`:** server-loaded profile + documents, then client `ProfileForm` (name, PAN, VAT, location, province, districts served, registration date, procurement types, sectors, services, certifications; licence rows with class A–D and last-renewed FY; turnover rows per FY with live lakh/crore preview; JV partners). Validation in `lib/company-form.ts` (FY `YYYY/YY` consecutive like `FiscalYearBS`, duplicates, amounts with commas or Devanagari digits). `KnowledgeBase`: file, doc type, **expiry date picker that follows the calendar toggle** (BS text input → shows AD; AD date input → shows BS; always sends `expires_on` AD), FY covered, value; table with type, expiry in both calendars + Expired badge, ingestion status badge, chunks, warnings; **polls every 2 s** while any doc is pending/processing. Upload is disabled until a profile is saved.
- **`/runs`:** placeholder page so the nav works (run log is the next UI task, issue 55).
- **shadcn/ui** components added with the real CLI: badge, card, input, label, table, textarea, separator, native-select, skeleton.
- **Tests:** `bun run test` gives **63 passed** (was 2): format (lakh grouping, crore/lakh short forms, Nepali digits), calendar (backend anchors incl. 2083-08-05 = 2026-11-21, every day 2075–2090 round-trips, 2084-03-32 valid, invalid dates, Devanagari digits), deadline (18:15 UTC rollover, `days_left` = 33 like the API test, 24 h hour display, passed states, en/ne text), i18n (same keys and placeholders in both languages, NFC, ≥95% Devanagari), data layer (filter parsing, FastAPI errors, reasons, mock ranking/filters, company form round trip and errors), and **one component test** (`components/__tests__/tender-row.test.tsx`: Nepali labels, Devanagari title rendered byte-identical/NFC with `lang="ne"`, `५ मंसिर २०८३ BS, १२:०० NPT`, `रु. १.४९ करोड`, live countdown `३३ दिन बाँकी`, toggles switch language/calendar and persist, cross-tab storage event, unextracted row). `bunx tsc --noEmit` and `bun run lint` clean. Backend: **605 passed, 4 deselected** (+2 export tests).
- **README.md "All commands"** (follow-up, same day): every runnable command grouped as setup, Docker, host run (with bash + PowerShell env vars and host URLs), demo data, hand-run API flow (filters, analyze, runs, override, proposal gate, company + upload `curl`s), agent CLIs and metrics, tests, maintenance. Each command is tagged with what it needs (offline / API / DB / Ollama). The CLI flags were checked against each script's argparse, and `score_matching` / `score_compliance` were re-run offline (unchanged numbers).
- **Verified in the dev server** (`NEXT_PUBLIC_USE_MOCKS=1 bun run dev`): `/`, `/?procurement_type=goods` (1 row), `/company`, `/runs` all 200; server HTML contains the Devanagari title and BS dates (`१९ कात्तिक २०८३`, `19 Kartik 2083 BS`) intact; the served CSS has the Noto Sans Devanagari `@font-face` with `unicode-range: U+900-97F … U+200C-200D` (ZWNJ/ZWJ for conjuncts). Without mocks and with no backend, `/` shows the "could not reach the API" message and `/company` the load error. Glyph shaping itself was not inspected in a real browser (no browser here).

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
- **Live scraper source is kankaimun.gov.np** (robots allows it, no terms page, no login). bolpatra, NEA, PPMO and Pokhara refused or reset our client, and we never work around that. The source is behind `TenderSource`; a second portal is out of scope.
- **Seed notices are the demo source.** `POST /tenders/scrape` defaults to `seed` and never touches the network for it (a test enforces this).
- **The scrape endpoint is synchronous**, capped at 10 notices (about 2-3 min live, instant from cache). A background job wasn't worth it for a bonus source.
- **Raw text only in `tenders`.** The scraper doesn't even set `title`. The page title is the first line of `raw_text`.
- **Changed raw text resets a tender** to `new` and drops its matches and compliance items (stale analysis of different text). Proposals are kept as human work.
- **Seed `source_url`s are `seed://seed_tenders/<file>`.** They are stable and can never collide with a scraped URL.
- **Demo story vs the demo KB:** every realistic current notice (including 001, the strong match) asks for an **FY 2082/83** tax clearance. The demo KB only has the **expired FY 2081/82** clearance, so 001 will fail `NP-TAX-CLEARANCE` until a fresh clearance is uploaded. 002 is the deliberate *other* hard fail (turnover, experience, class, JV barred), and it fails even with a fresh clearance. See Open issues 29.
- **The LLM fills `TenderExtraction`, not `TenderRecord` (Prompt 5b).** With raw strings only, the model has no path to put a converted date or amount into a typed field. `TenderRecord` is now entirely code-built.
- **Grounding is strict.** A raw value counts only if it occurs in the notice after folding whitespace, case, digit script (Devanagari ↔ ASCII) and quote style. A "helpful" conversion by the LLM (e.g. `NPR 14875000` for `Rs. 1,48,75,000/-`) is therefore treated as not verbatim: null + `needs_review`.
- **`needs_review` does not change status.** The tender is still `extracted`; flags live in `record_json.review_flags`, and there is no DB column (no migration). Matching/Compliance must treat a null deadline/cost as unknown (the rules already return `unclear`).
- **When a deadline cannot be confirmed, `deadline_bs_raw` is null too.** The raw string stays in `sources` / `review_flags`. Otherwise `nepal.rules._deadline` would re-parse a string Scout had rejected.
- **An "in thousands" notice:** any amount with no currency marker and no unit word is rejected (table cells). Prose amounts with `रु.` / `Rs` still parse.
- **"Tax clearance or tax return" is one `tax_clearance` doc.** Rule 40(2)(d) makes them alternatives, and listing both as mandatory would fail compliance wrongly.
- **Code adds a `bid_security` RequiredDoc** when the bid security was extracted and the LLM did not list it as a document.
- **Language is computed** from the Devanagari letter share (<0.02 en, >0.92 ne). The thresholds fit all 37 seeds; `[VERIFY]` on real notices.
- **Golden-set doc labels** use the rules written into `scout_expected.json`: documents to submit or hold; criteria-only evidence (turnover, experience) is excluded unless the notice names the document; non-standard documents count as `other`.
- **`python -m api.<module>` from `api/` (follow-up to Prompt 5b).** `api/` is a flat app, so there was no `api` package. `api/api/__init__.py` is an alias package whose `__path__` is `api/` itself, so `uv run python -m api.agents.scout --seed` and `python -m api.scripts.score_scout` work, and the flat `-m agents.scout` still works. App code keeps importing flat names; nothing may `import api.*`. A test (`test_cli_module_paths_import`) runs all three module paths. **It works from `api/` only.** From the repo root `uv run` finds no project (it would need a root uv workspace, which moves `uv.lock`/`.venv` to the root and breaks the api Dockerfile), so that was not done.

- **Matching splits code from judgement (Prompt 6).** Hard skips (type, area, capacity, deadline) are code. The LLM scores scope relevance only, and the prompt withholds the facts code owns, so the model can't double-count or override them. Code decides the score and the decision.
- **A hard skip caps the score at threshold-1**, not 0. The list still ranks skipped tenders by how close they were, and they never outrank a pursued one.
- **No LLM call on a hard skip** by default. Without the model, 26 of 37 seeds would each still cost a 7B call. `MATCH_LLM_ON_HARD_SKIP=true` restores it.
- **Capacity = cost <= 2.0x average turnover (last 3 FYs)** is company policy and configurable, not a Nepal rule. The notice's own turnover criterion stays with Compliance (`NP-TURNOVER`), and JV pooling is not considered in Matching.
- **"Sector overlap" is the model's job; "procurement type" is code's.** Sectors are free text (`"rural roads"`), so a deterministic overlap would be keyword guessing. The new `CompanyProfile.procurement_types` gives a clean enum check (empty = no filter). It is stored in `profile_json`, so no migration.
- **One `matches` row per tender**, replaced on re-run. The `reasons` JSONB holds the whole `MatchResult` dump (signals, scores, skip reasons, chunk ids), so detail views need no join and no migration.
- **Matching is allowed from `failed`** when a record exists (a retry after a model failure). `checked` and later are refused, because re-matching would bypass Compliance.

- **Compliance asks the model one requirement at a time (Prompt 7)**, each with its own retrieval. That is more calls (3 for seed 001), but each prompt is small, retrieval is specific, and every call has its own agent_runs row. A 7B model is more reliable on one question than on a list.
- **A model pass or fail must be grounded in code**: a cited chunk that was shown, and a verbatim quote from it. Otherwise it is `unclear`, with the reason in the explanation. This is an explicit downgrade, not silent coercion. A `fail` needs evidence too: no retrieved evidence is not proof of failure, and a mandatory fail blocks the bid.
- **Severity is code's**: mandatory requirement -> hard (task + CLAUDE.md). Rule items keep the severity in `rules.yaml`. Only `fail` + `hard` blocks; a hard `unclear` never does.
- **Profile entries are not evidence.** A pass needs a readable KB document, or (for rules) the notice itself. Profile figures still drive thresholds (turnover), but a pass also needs audit reports. JV and licence renewal are unclear until the agreement / licence copy is uploaded.
- **Per-bid forms (self-declaration, power of attorney) never fail.** They are signed for each bid, so their absence from the KB means "prepare it", not "ineligible".
- **Documents lapsing inside the bid validity period are `unclear` + "renew before" (soft)**, because the rule behind it is unverified. Expiry before the deadline stays a hard fail.
- **Override = accepting a specific set of hard failures.** It is stored with the failures' keys (`rule_id:requirement`) and stays active only while the current hard failures are a subset. Overrides are kept as history, never deleted, except when the notice text changes. The failures stay on the report, and status `checked` means "may proceed".
- **Re-analysis is allowed from checked/blocked** (upload a renewed document, then analyze again). `run_matching` alone still refuses those statuses; only the orchestrator passes `rematch=True`, and it always re-runs Compliance.
- **The demo KB gets a construction licence document (`06_...txt`).** The expired tax clearance stays as the deliberate blocker (issue 29 -> option a).

- **A pipeline run is its own record (Prompt 8).** `tenders.status` stays the state machine. `pipeline_runs` is the history of passes over it (stages, durations, errors), and agent_runs rows link to the run that wrote them. Stage results live in one JSONB column, because the UI reads a run whole and nothing queries individual stages.
- **Agents keep owning their status writes**; the orchestrator checks them against `TRANSITIONS` afterwards. That keeps the CLIs (`agents.scout --db`) working without the orchestrator, and a stage that breaks the table fails the run loudly.
- **Resume is derived, not stored.** There is no `failed_stage` column: each failing stage already deletes its partial output, so the stored data says how far the tender got, whoever ran it.
- **`stopped` is a separate run status from `failed`.** Skipped and blocked are expected business outcomes, and the Runs page should not show them as errors.
- **Background work = FastAPI `BackgroundTasks` plus a DB guard** (partial unique index, heartbeat reaper). No queue or APScheduler: one process, and a crash is recovered by the startup reaper and the next analyze.
- **Pre-cache = a replay cache inside `LLMClient`, not a DB snapshot.** On stage the real pipeline runs (deterministic code, retrieval, agent_runs, the Runs page animating), and only the model answers come from the file. The audit log stays honest (`cached=true`), and a miss falls back to the live model. The cost is that keys include prompts, so the KB chunk ids must match the recording (fresh DB + `--seed-company`; `--check` verifies).

- **The web app's BS calendar is exported from the backend, not a JS package (frontend prompt).** `nepali-date-converter` 3.4.0 (MIT, no network) was installed and cross-checked against `nepali-datetime` for every day 2010–2040 AD: identical through BS 2083, but it **disagrees in 2084–2087** (e.g. Jestha 2084 = 32 days vs 31; 212 days of 2084 differ) and stops at BS 2090. Future BS years are projections and sources differ, so the UI must show exactly what the API computes. It was removed; `scripts/export_bs_calendar.py` + a drift test keep one source of truth.
- **Vitest runs on `happy-dom`, not jsdom** (issue 14). jsdom fails under Bun when no Node is on PATH; happy-dom works, so the "Bun only" rule holds. jsdom was removed.
- **Preferences are client-only, data rendering is server-side.** Rows are server components; only labels, dates, money and countdowns are small client leaves reading the preferences. SSR always renders English + BS; the stored choice applies right after hydration (a brief flash for Nepali users, no hydration errors). Cookies would avoid the flash but make every page request-time and were not needed for the demo.
- **The URL is the dashboard filter state** (shareable, back button works); invalid params are dropped by `parseTenderFilters`, never sent.
- **Mocks are explicit, not automatic.** `NEXT_PUBLIC_USE_MOCKS=1` (build/dev-time; `NEXT_PUBLIC_*` is inlined into the client bundle) turns them on and shows a banner. Without it an unreachable API is shown as an error, so a demo can never silently present mock data as live.
- **Server fetches use `API_URL`** (compose: `http://api:8000`), the browser uses `NEXT_PUBLIC_API_URL`.
- **Expiry dates are always sent as AD** (`expires_on`), converted client-side with the exported table, so the BS picker and the API agree by construction.

## Deviations from spec
- §11 `tenders.budget` is named `estimated_cost_npr` (same meaning, integer NPR). Timestamps are `TIMESTAMPTZ`, not `TIMESTAMP` (NPT matters). `matches` has a serial `id` (spec has no PK). `agent_runs.tender_id` has no FK, as in the spec, because Scout runs before the tender row exists.
- `DocType.company_profile` added (capability statement; NEPAL_CONTEXT §11 updated).
- §10.2 `POST /tenders/scrape` "enqueue Scout": not done yet. Scout exists (Prompt 5b) but is not wired to the endpoint. It returns a `ScrapeReport` instead of `list[TenderDetail]`.
- §8.1 Scout output: the LLM emits `TenderExtraction` (raw strings) and code builds `TenderRecord`. The record is the same contract plus code-owned additive fields (`criteria`, `bid_security_due`, `sources`, `review_flags`, `needs_review`).
- §5.1 "one live portal scraper": the source is a municipal notice board, not a national portal. The national portal (bolpatra) blocks non-browser clients. And most live notices are scanned PDFs that yield no text without OCR (out of scope).
- None in behaviour. Additive fields beyond §8.1/§11: `TenderStatus.failed`, `AgentRunRecord.attempts/error/raw_output` (the `agent_runs` table needs these three columns when migrations land), `ReviewGap.severity`, `ComplianceItem.explanation`. (The spec allowed bge-m3 *or* nomic-embed-text; choosing bge-m3 is a selection within the spec.)
(Prompt 3 note, superseded: §8.2 was re-read in Prompt 5b; §13 still not re-read.)

- §11 `matches.reasons` stores the full `MatchResult` JSON (an object), not just a reasons array. §10.2 `GET /tenders` returns `TenderListItem`s (not `TenderDetail`s). `POST /tenders/{id}/analyze` runs Matching only until Compliance exists.

- §11 `compliance_items` gained structured evidence columns + `action_needed` + `source`, plus a new `compliance_overrides` table (spec has none; the override is required by this task). `evidence` (TEXT) is kept as a readable summary.
- §10.2: a new route `POST /tenders/{id}/compliance/override`; `POST /tenders/{id}/proposal` now has a 409 gate (still 501 behind it). `TenderDetail.compliance` is a `ComplianceView`, not a bare `ComplianceReport`.
- §10.2 (Prompt 8):
  - `GET /runs/{id}` returns a **pipeline run** (`PipelineRunDetail`: stages + durations + its agent_runs rows), not a single agent_runs row. There is a new `GET /runs` list.
  - `POST /tenders/{id}/analyze` returns 202 + the run (background task) instead of the tender detail, and it also runs Scout on a `new` tender. `POST /tenders/scrape` still does not enqueue anything.
- §11: a new `pipeline_runs` table; `agent_runs` gains `pipeline_run_id` (FK) and `cached`.
- §9.1 (frontend prompt): `/runs` is a placeholder and `/tenders/[id]` and `/tenders/[id]/proposal` do not exist yet. Dashboard rows show reasons and hard-failure counts but do not link anywhere.

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
16. Verify spec §13 against api/nepal/ (§8.1/§8.2 were read in Prompt 5b and are reflected in Scout).
17. ~~`nepali-datetime` tests not run~~: run in Prompt 4. All pass after fixing one wrong test assertion. The library range (about 1975-2100 BS) is still its own limit.
18. ~~`TenderRecord` has no structured turnover/experience criteria~~: Prompt 5b put `TenderCriteria` on the record, and Scout fills `min_avg_turnover_npr`, `min_similar_value_npr`, and `turnover_years` when exactly one count is stated. Still not extracted: `min_similar_projects` (NP-EXPERIENCE stays `unclear` until it is), and "best 3 of the last 5 years" is left as null years.
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
14. ~~`bun run test` fails on this machine~~: **fixed in the frontend prompt** by switching Vitest to `happy-dom`. Original note: There is no Node.js on PATH, so vitest's worker runs under Bun and jsdom throws `addEventListener ... not a valid instance of EventTarget`. Prompt 1 verified it elsewhere. Options: switch the vitest environment to `happy-dom`, or document Node as a test-runtime requirement. Needs a team call (CLAUDE.md says Bun only).
15. `bunx tsc --noEmit` reports `Cannot find name 'LayoutProps'` in `app/layout.tsx`. That is a Next.js-generated global that only exists after `next build`/`next typegen`, so it is not a real error. `bun run build` remains the type-check of record.

New (Prompt 4):
23. **Seed with real embeddings not run.** No Ollama on this machine, so run `uv run python -m scripts.seed_demo` once `bge-m3` is pulled (issue 12/13).
24. **Docker image not rebuilt/verified** after the Dockerfile change (migrations on start, `--no-dev`). There is no Docker here. Check with `docker compose up --build`. The seed runs from the host, because `data/` is outside the api build context.
25. **`bun run build` fails on this machine at "Collecting page data"** (`Expected CommonJS module to have a function wrapper ... bug in Bun`). It is identical on clean HEAD, and TypeScript type-checking passes. Same root cause as issue 14 (no Node on PATH).
26. Duplicate uploads (same `sha256`) are allowed. Add a dedupe or replace option if the UI needs it. There is no re-ingest or delete endpoint yet (the seed re-ingests by deleting and recreating).
27. No Preeti-to-Unicode conversion; such PDFs only get a warning (NEPAL_CONTEXT section 9).
28. Starlette warns that `TestClient` with `httpx` is deprecated (`httpx2`). Not ours to fix yet.

New (Prompt 5a):
29. **Decided in Prompt 7: option (a)** (expired clearance kept as the demo beat; a licence copy was added instead). **Demo KB vs strong match:** 001 (and 015/016/019/029) will fail `NP-TAX-CLEARANCE` against the demo company's expired FY 2081/82 clearance. Team call: (a) keep it as a demo beat (blocked, upload FY 2082/83 clearance, unblocked), or (b) add a valid FY 2082/83 tax clearance to `data/demo_company/` (manifest + `build_demo_docs.py`) so 001 passes cleanly and the expired one is just history.
30. ~~Nepal-layer parsing gaps~~: **fixed in Prompt 5b** (`parse_deadline`, strict grouping + compound amounts in `parse_npr`). `deadline_from_raw` itself is unchanged; Scout uses `parse_deadline`. Original note: `deadline_from_raw` fails on `"2083-08-05 B.S. (2026-11-21 A.D.)"` (BS+AD in one string), `"…१२ बजे"` (hour without minutes) and `"15/08/2083 by 12 noon"`. Scout must pass only the BS date part, or the normaliser should strip the bracketed AD and bare hours. `parse_npr` rejects compound amounts (`"रु. ३२ लाख ५० हजार"`), and **silently accepts mis-grouped digits** (`"Rs. 1,50,000,00"` → 15,000,000) where it should flag invalid lakh grouping.
31. **Live scraper yields little:** both live tender notices on 2026-10-19 were scanned PDFs. Without OCR (out of scope) the live path is a demonstration of polite scraping, not a data source. The robots.txt fetch also saw an intermittent connection reset (the run then fetches nothing).
32. Kankai's terms of use: no page was found. Re-check before any heavier or scheduled use. APScheduler is not wired to the scraper, and should not be without that check.
33. Seed notice conventions (e.g. "within 15 days of publication", "in thousands" tables, corrigenda) come from general knowledge of Nepali notices, not a sampled corpus `[VERIFY]` against real notices if the Scout golden set is to be representative.
34. Docker: the seed volume mount and compose change are not verified (no Docker on this machine, same as issue 24).

New (Prompt 5b):
35. **Scout has never run against a real model, so there are no accuracy numbers.** First thing once Ollama is up (issues 12/13): `cd api && uv run pytest -m ollama` (does the grammar accept `TenderExtraction`?), then `uv run python -m api.scripts.score_scout --manifest --out ../data/golden/report.json`, and record the numbers here. Expect the weak spots to be verbatim copying of Devanagari, picking the submission deadline rather than the opening date, and doc lists.
36. Golden set: 10 of 15 entries are `todo` (004, 006, 007, 008, 011, 015, 021, 027, 033, 034). Their deadline/cost labels already exist in the manifest (`--manifest` scores them); the required-doc labels need a hand pass.
37. Prompt size: the system prompt is about 1.1k tokens, plus the notice. With `LLM_NUM_CTX=8192` that is fine for seed notices, but long PDF attachments from the live scraper may exceed it. There is no chunking or truncation guard yet.
38. The `दिनको` + hour 1–5 = PM heuristic and the language thresholds are unverified against real notices (NEPAL_CONTEXT §13 `[VERIFY]`).
39. `needs_review` is now in the API (Prompt 6: `TenderListItem.needs_review`; `GET /tenders/{id}` returns `record.sources` / `review_flags`) but has no UI yet. The UI should show `sources[].quote` next to each value and highlight `review_flags`.

New (Prompt 6):
40. **Matching has never run against a real model, so there are no model numbers.** Once Ollama is up: `uv run pytest -m ollama` (does the grammar accept `MatchAssessment` in context?), then `uv run python -m api.scripts.score_matching --llm --out ../data/golden/match_report.json`. Expect core@3 to rise from 0.33 and 007/037 to drop below the threshold; record the numbers here. Then repeat with `--records` from real Scout output (issue 35), which measures Scout + Matching together.
41. The metric's `--llm` mode sees **no KB chunks** (no DB in the script) and oracle titles are file slugs. The API path (`run_matching`) does retrieve chunks. A DB-backed metric mode would measure retrieval too.
42. Weights and points (0.6 / 30-30-25-15 / threshold 60 / cap 2.0x / tight 7 days) are first guesses. Tune them only against `match_relevance.json` with the real model, and watch out for overfitting 37 synthetic notices.
43. ~~`GET /tenders` has no compliance status~~: Prompt 7 added `hard_failures` per row. Still no full-text search.

New (Prompt 7):
44. **Compliance has never run against a real model.** Once Ollama is up: `uv run pytest -m ollama`, then `uv run python -m api.scripts.score_compliance --llm --out ../data/golden/compliance_report.json`. Record recall / hard-fail recall here; the target is hard-fail recall 1.0 (002 class A/B and batching plant) with 0 false hard fails. Then `--records` with real Scout output (issue 35): Scout's requirement lists decide what the model layer even sees.
45. **Experience stays `unclear`** on every demo tender: `DocumentMeta.similar` is never set (issue 19, classifier half) and Scout does not extract `min_similar_projects` (issue 18). A deterministic "similar work" classifier, or a user tick on upload, would turn 001/015/016/019/029 experience into a pass.
46. **Turnover stays `unclear`** when the notice says "best 3 of the last 5 years" (Scout leaves `turnover_years` null) and because the demo KB has no `audit_report` documents. Supporting "best N of M" in `TenderCriteria` + NP-TURNOVER, and adding audited statements to the demo KB, would fix both.
47. `covering_rules` / `_RESIDUAL` are keyword lists tuned on 7 synthetic notices (English + Nepali). Real notices will word things differently `[VERIFY]`; a miss means a requirement is judged only by the rule (if covered) or only by the model.
48. No UI yet for the compliance checklist, `action_needed` or the override form (who/why). The web app should show `evidence_quote` next to the chunk and the document link.
49. ~~Analyze is synchronous~~: fixed in Prompt 8 (background run + replay cache).

New (Prompt 8):
50. **`data/demo_cache/llm_cache.json` has not been recorded.** On the demo machine with Ollama up and a fresh DB: `cd api && uv run python -m api.scripts.precache_demo --seed-company`, then `--check`. Decide whether to commit the file. It is plain JSON of synthetic-notice outputs plus about 1024 floats per chunk/query, so expect a few MB.
51. Replay keys include the prompts, and prompts cite KB chunk ids. Re-seeding a non-fresh DB (`seed_demo` deletes and re-inserts documents, so ids grow) makes Matching/Compliance miss, which means live model calls. `--check` detects this. A content-addressed chunk citation would remove the coupling, but that is a prompt and contract change.
52. The reaper's stale threshold (600 s) assumes a stage makes progress at least every 2×`LLM_TIMEOUT_S`. A Compliance stage with many requirements bumps the heartbeat per call, so it is fine. A worker that is still alive but past the threshold is marked failed, yet still writes its real outcome when it finishes.
53. Background tasks share the process with the API. With several uvicorn workers, the startup reaper of one worker would fail another worker's live runs. Run a single worker (the Docker CMD does today), or reap by age only.
54. Proposal/Review runners are `None`. When those agents land:
    - extend `resume_status` (a proposals row means `checked` was completed);
    - wire them in `default_runners`;
    - implement "review fail → one revision pass" (spec §10.3);
    - `POST /proposals/{id}/approve` is the human `reviewed→approved` edge.
55. No UI yet for the Runs page / polling (spec Day 6, member C). The API is ready: `GET /runs`, `GET /runs/{id}`, and analyze returns the run id. (Frontend prompt: `/runs` is a placeholder page only.)

New (frontend prompt):
56. **`bun run build` still fails here** (issue 25, Bun + no Node). Not re-tested beyond that; the dev server, `tsc` and lint pass. The Docker image (oven/bun) builds with `bun run build` too, so check `docker compose up --build` on a machine with Docker.
57. **Not run against a live API.** Only mock mode and the "API unreachable" path were exercised. With the backend up: load seeds, analyze a few tenders, and check the dashboard, filters (especially a Nepali `district`), the profile round-trip and a real upload → ingest status poll.
58. **No real-browser check of Devanagari shaping.** Tests verify code points, NFC, `lang` and the font's unicode-range; nobody has looked at conjuncts (`च्छ्रे`, `ण्ड`) on screen. Open `/` in Nepali mode once and eyeball it (and print to PDF later for the export path).
59. **No `/tenders/[id]` page yet**, so rows are not links. It needs the extracted fields with `sources[].quote` (issue 39), match signals and the compliance matrix (issue 48).
60. Nepali UI labels were written by the model, not a native speaker `[VERIFY]` (e.g. "राष्ट्रिय बोलपत्र" for NCB, "सिलबन्दी दरभाउपत्र" for sealed quotation, "कर चुक्ता प्रमाणपत्र" for tax clearance). Have a Nepali reader review `lib/i18n/dict.ts`.
61. Mock state is per tab in the browser and per process on the server, so a saved mock profile disappears on reload (the banner says so).
62. A frontend BS date outside BS 2000–2099 falls back to AD display; the BS input rejects it.

Other:
- The spec's AI-disclosure table (§15.1) is garbled in the PDF text extraction. Function names will be finalised from real code.

## Next prompt
Prompt 9: get a real model running (issues 12/13), then measure everything that is still unmeasured: `pytest -m ollama`, `score_scout --manifest` (35), `score_matching --llm` (40) and `score_compliance --llm` (44). Record the numbers and tune the prompts only against those misses. Then record the demo replay cache (issue 50: `precache_demo --seed-company`, then `--check`). After that:
- optionally let `POST /tenders/scrape` start pipeline runs (`orchestrator.start_run` + `execute_run` per new tender, target `extracted` or `checked`);
- start the Proposal agent as the orchestrator's Proposal runner (issue 54) behind `agents.compliance.proposal_allowed` (RAG per section, cite chunk ids, use the compliance report's `action_needed` items as known gaps);
- optional quick wins for compliance quality: "best N of M" turnover (46) and the experience `similar` classification (45).

Frontend track (parallel, can be a separate prompt): run the web app against the live API once (issue 57) and eyeball Nepali rendering in a browser (58). Then build `/tenders/[id]` (59): extracted fields with `sources[].quote` next to each value and `review_flags` highlighted (39), match signals, the compliance matrix with green/red/amber rows and an expandable evidence cell (spec §9.2, issue 48), the override form (who/why), and an "Analyze" button that polls `GET /runs/{id}` every 2 s. Then the real `/runs` log (55).
