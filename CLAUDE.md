# Tenderly

## Project summary

Tenderly is an agentic tender-to-proposal platform for Nepali SMEs. It scouts public tender notices, extracts them into structured records, scores each against a company profile, checks eligibility and compliance against the company's knowledge base, drafts a proposal grounded in that knowledge base, reviews the draft, and produces a submission-ready package after a human approves it. The pipeline is `Scout → Match → Compliance → Proposal → Review → Human approval → Package`. Each stage emits typed JSON that code consumes to route, filter, block or gate the next stage. For example, a low match score skips the tender, and a hard compliance failure blocks proposal generation.

The scope is set by a two-week, three-person build (Frogtoberfest). In scope: one live portal scraper plus a seeded dataset of 30–40 tenders, matching, compliance checking, RAG proposal generation, automated review, human approval, and DOCX/PDF package export, with an audit log of every agent run. Out of scope: automated portal submission, multi-tenant billing and accounts, OCR, multi-portal support, notifications, payments, and fine-tuning. The full spec is [docs/Tenderly_spec.pdf](docs/Tenderly_spec.pdf). Nepal-specific procurement facts are in [docs/NEPAL_CONTEXT.md](docs/NEPAL_CONTEXT.md).

**Demo claim:** "From a raw tender notice to a compliance-checked, reviewed proposal package in minutes, with a human approving every critical step."

## Hard rules

1. **Open-weight models only.** Serve them with Ollama. The LLM is `Qwen2.5-7B-Instruct` (fallback: Llama 3.1 8B) and the embedding model is `bge-m3`. **Embedding dimension is fixed at 1024**: `kb_chunks.embedding VECTOR(1024)` (migration `0001`) and `pipeline.llm.EMBED_DIM`. Changing the model or dimension needs a new migration and a full re-embed. The endpoint comes from the `LLM_BASE_URL` / `LLM_MODEL` env vars (context window `LLM_NUM_CTX`, default 8192), and any hosted fallback must serve open-weight models only.
2. **No proprietary APIs anywhere**, including default embeddings in libraries. Audit dependencies before adding them.
3. **All LLM and embedding calls go through one client: `api/pipeline/llm.py`.** No other module may import an HTTP client to talk to a model.
4. **Every LLM output is JSON-schema constrained** (Ollama `format` = the Pydantic model's JSON schema) **and Pydantic validated.** Invalid output gets one retry, and if that fails the stage is marked `failed`. Never silently coerce.
5. **Deadline, budget, document-expiry and score-threshold checks are deterministic code**, never LLM judgment. The LLM only extracts the values.
6. **Nothing is ever submitted externally.** No stage logs in to, posts to, or uploads to any portal.
7. Use temperature 0 for extraction, matching, compliance and review, and low to moderate temperature for proposal text.
8. Proposal sections must cite KB chunk ids. Compliance evidence without a chunk id is `unclear`, never `pass`.
9. Every stage writes an `agent_runs` row (stage, model, input hash, output JSON, latency, ok).
10. Do not invent Nepal procurement thresholds. Use [docs/NEPAL_CONTEXT.md](docs/NEPAL_CONTEXT.md) and respect its `[VERIFY]` markers.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui, typed API client via `openapi-typescript` |
| JS tooling | **Bun only.** Use `bun install`, `bun run <script>`, `bunx <tool>`. Never use `npm`, `yarn`, `pnpm`, `npx` or `node` commands. |
| Backend | FastAPI + Pydantic on Python 3.11, managed with **uv** (`uv sync`, `uv run`, `uv add`) |
| Database | PostgreSQL + pgvector |
| Models | Ollama (Qwen2.5-7B-Instruct, bge-m3) |
| Ingestion | httpx, BeautifulSoup (Playwright only if needed), PyMuPDF, python-docx |
| Export | python-docx, WeasyPrint or ReportLab |
| Scheduling | APScheduler |
| Tests | pytest, Vitest, Playwright (one E2E test) |
| Deployment | Docker Compose (web, api, postgres+pgvector, ollama) |

## Repo layout (spec §10.1)

```text
Tenderly/
  web/                 # Next.js + TypeScript
    app/               # /, /company, /runs, /tenders/[id]
    components/        # app-shell, tenders, tender-detail, company, ui (shadcn)
    lib/               # api/ (client, types, enums), mock/, i18n/, nepal/
                       # format.ts, deadline.ts, prefs.tsx, review-flags.ts
      api/
      mock/
        detail-api.ts
      i18n/
        dict.ts
        detail-messages.ts
      nepal/
        calendar.ts
    components/
      tender-detail/
    app/
      tenders/
        [id]/
          page.tsx
  api/
    main.py
    routers/            # tenders.py, company.py, proposals.py, runs.py, reference.py
    agents/             # scout.py, matching.py, compliance.py, proposal.py, review.py
    pipeline/           # orchestrator.py (state machine), llm.py (Ollama client)
    schemas/            # Pydantic models shared by all stages
    ingest/             # parse_docs.py, chunking.py, embed.py, kb.py (upload -> parse -> chunk -> embed);
                        # notices.py (RawNotice + upsert), seed_tenders.py, scraper.py (live: kankaimun.gov.np)
    db/                 # models.py (SQLAlchemy 2), session.py, search.py (pgvector top-k cosine), runs.py (agent_runs recorder)
    alembic/            # migrations (source of truth for the live schema); alembic.ini in api/
    scripts/            # seed_demo.py, build_demo_docs.py, score_scout.py, score_matching.py, score_compliance.py (metrics),
                        # precache_demo.py (records/checks the demo LLM replay cache), export_bs_calendar.py (BS table -> web)
    deps.py             # FastAPI deps: get_session, get_sessionmaker, get_llm_client (tests override)
    api/__init__.py     # alias package only: makes `python -m api.<module>` work from api/ (app code imports flat names)
    export/             # docx.py, pdf.py, package.py
    tests/
  data/demo_company/    # FICTIONAL demo SME: profile.json, manifest.json, 6 KB documents (tax clearance FY 2081/82 EXPIRED on purpose)
  data/seed_tenders/    # 37 SYNTHETIC tender notices (.txt) + manifest.json with labelled ground truth
  data/golden/          # scout_expected.json (Scout), match_relevance.json (Matching), compliance_requirements.json (Compliance: 54 mandatory requirements, 7 seeds)
  docker-compose.yml
  README.md
  ARCHITECTURE.md
  AI_DISCLOSURE.md
  LICENSE
```

- **Nepal layer:** `api/nepal/` (`numbers.py`, `dates.py`, `geography.py`, `documents.py`, `rules.yaml`, `rules.py`). Deterministic, no LLM. Rules evaluator: `nepal.rules.evaluate_rules(tender, company, documents, criteria=, now=)` returns `ComplianceItem`s with `rule_id` (criteria default to `tender.criteria`). Scout parsers: `parse_deadline(raw)` → `DeadlineParse` (BS/AD/time, `issues` instead of guesses), `parse_npr` (strict grouping, compound "32 lakh 50 thousand"), `parse_percent`, `parse_days`, `documents.classify_document` / `find_fiscal_years`. Import from `nepal`.

Tender status state machine (`pipeline/orchestrator.py::TRANSITIONS`, spec §10.3):

```text
new --Scout--> extracted --Matching--> matched --Compliance--> checked --Proposal--> drafted --Review--> reviewed --human--> approved
                          |                                  |
                          +--> skipped                       +--> blocked --human override--> checked
any stage --LLM invalid after one retry / timeout / crash / illegal edge--> failed --next run resumes at the last good state
```

`skipped` = score below threshold or a deterministic hard skip (Compliance does not run). `blocked` = a hard compliance failure (no proposal unless overridden). Agents commit only these resting statuses. A failed tender's resume point is derived from stored data (`resume_status`: no record → Scout; no match row → Matching; pursued match → Compliance). `approved` is only ever set by a person.

## Contract layer

- **Schemas:** `api/schemas/`, one module per stage (`tender.py`, `match.py`, `compliance.py`, `proposal.py`, `review.py`), plus `company.py`, `runs.py` (agent_runs record), `views.py` (API response shapes), `enums.py` (all enums, Nepal ones documented in [docs/NEPAL_CONTEXT.md](docs/NEPAL_CONTEXT.md) §11) and `_base.py` (the `Contract` base with `extra="forbid"`, `FiscalYearBS`, `BSDateISO`). Import from `schemas`.
- **The LLM fills only these models:** `TenderExtraction` (`schemas/scout.py`: verbatim `{value, quote}` strings, no conversions), `MatchAssessment`, `ComplianceAssessment` (ONE requirement: status, chunk ids, quote, explanation; no severity or rule_id), `ProposalSection`, `ReviewReport`. Code derives the rest: `agents.matching.combine` builds `MatchResult` (score + pursue/skip) from deterministic signals and the `MatchAssessment`, deterministic rules add `ComplianceItem`s with `rule_id`, and `ComplianceReport.is_blocked` does the gating.
- **LLM client:** `pipeline.llm.LLMClient(run_recorder, settings=None, transport=None, timeout_s=None, cache=None)`. `chat(stage=, messages=, schema=, tender_id=, temperature=)` returns a validated model or raises `LLMOutputError` / `LLMTransportError`, and always calls `run_recorder(AgentRunRecord)` exactly once. Temperature is fixed per stage (`STAGE_TEMPERATURE`), and only `proposal` may be overridden (≤0.7). `embed(texts)` returns `EMBED_DIM` (1024) vectors and writes no agent_runs row. **Replay cache:** `ReplayCache` (setting `LLM_REPLAY_CACHE`, read-only; docker-compose points it at `data/demo_cache/llm_cache.json`) answers a request whose hash (model, stage, messages, schema, temperature) it holds, re-validated strictly, with the agent_runs row marked `cached`. Misses call the model. `scripts/precache_demo.py` records it.
- **Database:** SQLAlchemy 2 models in `api/db/models.py` mirror spec §11 plus Nepal columns. Enum columns are TEXT with CHECK constraints from `schemas/enums.py`, so adding an enum value needs a migration. `tests/test_db.py::test_migration_matches_models` fails if models and migrations drift. Create migrations with `uv run alembic revision --autogenerate -m ...`, then review them by hand.
- **KB ingestion:** `POST /company/documents` stores the file and runs `ingest.kb.ingest_document` as a background task. The result lives in `documents.ingest_status` (`IngestStatus`: pending/processing/ready/needs_ocr/failed). Scanned PDFs become `needs_ocr` (no OCR). Chunks are 400–600 *estimated* tokens with 80 overlap (`ingest/chunking.py`). Retrieval goes through `db.search.search_chunks(session, vector, k, company_id=, doc_types=)` or `db.search.retrieve(session, client, query, k)`, and only `ready` documents are searched. Cite `ChunkHit.chunk_id`.
- **Tender ingestion:** `POST /tenders/scrape` (`ScrapeRequest`, default `{"source": "seed"}`) loads `data/seed_tenders/` (setting `SEED_TENDERS_DIR`; mounted read-only in Docker) or, with `"source": "kankai"`, runs the live scraper. Both produce `ingest.notices.RawNotice`s, and `upsert_notices` upserts them by `source_url` (seeds are `seed://seed_tenders/<file>`). New rows get status `new` and **raw text only**; Scout does all extraction. Identical text leaves a row (and its pipeline progress) untouched. Changed text resets it to `new`, clears derived columns and drops its match/compliance rows. The seed set is the demo source, and the scraper is a bonus that must never be a dependency (spec §17). The scraper enforces the robots, delay, UA and no-login rules in `ingest/scraper.py`'s docstring. Don't loosen them. Source findings are in NEPAL_CONTEXT §6. Scout is **not** enqueued from the scrape endpoint; `POST /tenders/{id}/analyze` runs it on a `new` tender.
- **Scout (`agents/scout.py`):** `extract_tender(client, raw_text, tender_id=)` = one LLM call (`TenderExtraction`) + `postprocess(extraction, raw_text)`, which is pure code. It builds the `TenderRecord` with the Nepal layer, checks every raw string and quote is in the notice (`Grounder`: tolerant only of whitespace, case, digit script and quote style), and stores `sources[]` (value, raw, quote, char span in `tenders.raw_text`) for value-next-to-source UI. If a raw string is not verbatim or does not parse, the value is null, a `ReviewFlag` is added and `needs_review` is true. Never guess. `language` is computed (Devanagari share), not asked of the LLM. `run_scout(session, client, tender)` / `scout_new_tenders` write the row and set `extracted` or `failed`. The agent_runs row keeps the raw LLM extraction; `record_json` keeps the derived record.
- **Matching (`agents/matching.py`):** `score_tender(record, company, chunks, client=, settings=, now=)`. `deterministic_signals` gives fit points (procurement type 30, district/province served 30, cost vs `MATCH_MAX_COST_TO_TURNOVER` × average turnover 25, deadline in NPT 15); a failed check is a **hard skip**. If nothing hard-skips, the LLM fills `MatchAssessment` (scope relevance only; the prompt withholds deadline, cost and location). `combine` gives score = `MATCH_LLM_WEIGHT` × semantic + rest × deterministic, a hard skip caps it at threshold-1, and the decision is code. Every reason is prefixed `[deterministic]` or `[model]`. `run_matching(session, client, tender)` retrieves top-k KB chunks (`MATCH_TOP_K`, skipped on a hard skip), replaces the tender's `matches` row (`reasons` JSONB = the full `MatchResult` dump) and sets `matched` / `skipped` / `failed`. A code-only run writes its own agent_runs row (`model="deterministic"`). `CompanyProfile.procurement_types` (empty = no filter) drives the type check. `pipeline.orchestrator.analyze_tender` runs Compliance only on `matched`. Settings: `MATCH_THRESHOLD` (60), `MATCH_LLM_WEIGHT` (0.6), `MATCH_MAX_COST_TO_TURNOVER` (2.0), `MATCH_TURNOVER_YEARS` (3), `MATCH_TIGHT_DEADLINE_DAYS` (7), `MATCH_TOP_K` (5), `MATCH_LLM_ON_HARD_SKIP` (false). These are company policy, not procurement law.
- **Tender API:** `GET /tenders` ranks by match score desc, then deadline asc, with unscored tenders last. Filters: `procurement_type, method, province, district` (EN/NE, normalised), `buyer_level` (from `record_json`), `min_score`, `deadline_within_days` (not passed, ≤N NPT calendar days), `language`, `decision`, `status`, `limit/offset`. Each row has `deadline: DeadlineView` (AD, BS ISO/long/Devanagari, `days_left`, `passed`), all from `nepal.dates`. `GET /tenders/{id}` → `TenderDetail` (+ `deadline_view`). `POST /tenders/{id}/analyze` runs Matching (409 if not extracted/matchable or there is no company). The clock comes from `deps.get_now` (tests pin it).
- **Reference API (`routers/reference.py`):** `GET /rules` returns rule metadata, including the rule description and verification state used by the tender-detail compliance matrix badges and `#rule-<id>` anchors. `GET /chunks?ids=` returns KB chunk text and associated document details for cited compliance evidence. The tender-detail page also uses `GET /company/documents` to resolve the documents cited by compliance items.
- **Compliance (`agents/compliance.py`):** `check_requirements(tender, company, documents, client=, retrieve_fn=, now=)` = Layer 1 `nepal.rules.evaluate_rules` (14 rules, `rules.yaml`; NP-OTHER-DOCS must stay last) + Layer 2: each `TenderRecord.requirements` entry the rules do not fully cover (`covering_rules` / `needs_model`: keyword routing; licence class, personnel, equipment, liquid assets ...) gets its own KB retrieval and one `ComplianceAssessment` at temp 0. `ground()` checks in code that cited chunk ids were shown and the quote is verbatim in a cited chunk, else pass/fail becomes `unclear`. Severity is code's (mandatory -> hard). Every `ComplianceItem` has `source` (rule/model), `evidence_chunk_ids`, `evidence_document_ids`, `evidence_ref` (rules may cite `tender.*`), `action_needed` (plain language, null on pass). A pass needs a chunk or document (validator). `run_compliance` (from matched/checked/blocked) replaces `compliance_items`, writes a `deterministic` agent_runs row for the rules layer, sets `checked`/`blocked` (or `failed`). Override: `POST /tenders/{id}/compliance/override` (`overridden_by`, `reason`) stores a `compliance_overrides` row with the accepted hard-failure keys and sets `checked`; it stays active only while every current hard failure is among them. `proposal_allowed()` gates `POST /tenders/{id}/proposal` (409 while blocked). `POST /tenders/{id}/analyze` = Matching (`rematch=True`) then Compliance; a no-longer-pursued tender loses its stale items. `GET /tenders/{id}.compliance` is a `ComplianceView` (items, blocked, hard_failures, counts, override, proposal_allowed); `GET /tenders` rows carry `hard_failures`.
- **Orchestrator (`pipeline/orchestrator.py`):** `POST /tenders/{id}/analyze` (optional `AnalyzeRequest {target=checked, from_stage}`) calls `start_run` (a `queued` `pipeline_runs` row, 409 if the tender already has a queued/running run; a partial unique index enforces it) and returns **202 + `PipelineRunView`**. `execute_run` then runs in a FastAPI `BackgroundTasks` (no queue). Each step's runner (`default_runners`: `run_scout`, `run_matching(rematch=True)`, `run_compliance`; Proposal/Review `None` until built) must move the tender along a legal `TRANSITIONS` edge. Otherwise, or if it raises, the tender becomes `failed` and an agent_runs row with `model="orchestrator"` is written. Runs end `succeeded` / `stopped` (skipped/blocked branch) / `failed`. `db.runs.pipeline_run_context` links every agent_runs row written during a run (`pipeline_run_id`). `reap_stale_runs` fails queued/running runs at startup (lifespan) and on `GET /runs*` once the heartbeat is older than `PIPELINE_STALE_AFTER_S`. Poll with `GET /runs/{id}` (`PipelineRunDetail`: stages with from/to status and `duration_ms`, plus agent_runs); list with `GET /runs?tender_id=&status=`. Scripts and tests use `run_pipeline(factory, client, tender_id, ...)` (synchronous; `runners=` injects stages).
- **Frontend (`web/`):** Next.js 16 with `cacheComponents` on, so pages that fetch call `connection()` and sit inside `<Suspense>` (read `node_modules/next/dist/docs/` before using a Next API; it differs from older versions).
  - `lib/api/tenderly.ts` is the only place pages call the API (typed from `lib/api/types.ts` via `getApiClient()`), with the mock fallback in `lib/mock/` behind `NEXT_PUBLIC_USE_MOCKS=1` (build/dev-time flag, shows a banner). `lib/api/enums.ts` holds runtime enum lists, checked exhaustively against the generated types. Server components fetch from `API_URL` (compose: `http://api:8000`), the browser from `NEXT_PUBLIC_API_URL`.
  - **Labels:** every UI string goes in `lib/i18n/dict.ts` in both `en` and `ne` (a test enforces same keys/placeholders, NFC). Use `usePrefs().t()` / `.label()` in client components and `<T k=…/>` / `<EnumText/>` in server components. Data (titles, buyers) is never translated.
  - **Dates and money:** BS dates come from the API's `DeadlineView` when available; otherwise use `lib/nepal/calendar.ts`, whose table `lib/nepal/bs-calendar.json` is **generated from the backend** (`cd api && uv run python -m api.scripts.export_bs_calendar`; never add a JS BS library, they disagree from BS 2084). Countdowns use `lib/deadline.ts` (NPT calendar days = API `days_left`), money `lib/format.ts` (lakh/crore). Respect the BS/AD and language preferences (`lib/prefs.tsx`, localStorage).
  - UI components come from the shadcn CLI (`bunx --bun shadcn@latest add <name>`, base-ui flavour); don't hand-write them.
  - Vitest runs on `happy-dom` (jsdom breaks under Bun without Node). Tests live in `__tests__/` next to the code.
  - **Tender detail** (`app/tenders/[id]/page.tsx` → `components/tender-detail/`): `loadTenderBundle(id)` returns the `TenderDetail` plus the chunk text and documents its compliance items cite (`GET /chunks`, `GET /company/documents`). `GET /rules` gives rule description/verified for the matrix badges (`#rule-<id>` anchors). Analyze polls `GET /runs/{id}` every 2 s (`RUN_POLL_MS`). Generate proposal needs `compliance.proposal_allowed`; the override dialog (`OverrideDialog`, shadcn `dialog`) records the override first. Needs-review logic lives in `lib/review-flags.ts`. New labels go in `lib/i18n/detail-messages.ts` (merged into `dict.ts`). Mocks: `lib/mock/detail-api.ts` (tenders 1 and 27).
- **Tests:** use `httpx.MockTransport` (see `FakeOllama` in `api/tests/conftest.py`; `MockKankai` in `tests/test_scraper.py` serves saved HTML from `tests/fixtures/scraper/`). Never hit a real model or a real website in the default suite. DB tests use `TEST_DATABASE_URL` if set, else an embedded Postgres+pgvector from the `pgserver` dev dependency (fixtures `session_factory` / `db_session` in conftest; tables are truncated per test). `bag_of_words_vector` is a deterministic fake embedder for retrieval tests.

## Session protocol

- **At the start of every task:** read `CLAUDE.md`, `PROGRESS.md` and `docs/NEPAL_CONTEXT.md`.
- **At the end of every task:** update `PROGRESS.md` (Done, Decisions, Deviations from spec, Open issues, Next prompt). Also update `CLAUDE.md` and/or `docs/NEPAL_CONTEXT.md` if anything they describe changed (commands, layout, rules, verified facts).
- Never overwrite these three files wholesale. Edit them in place.

## Commands

| Purpose | Command |
|---|---|
| Start full stack | `docker compose up --build` (first time / after Dockerfile changes), `docker compose up` after |
| Stack with NVIDIA GPU for Ollama | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d` (without it Ollama runs on CPU and Scout hits `LLM_TIMEOUT_S`; check `docker compose exec ollama ollama ps` says `100% GPU`) |
| Pull models | `./scripts/setup.sh` (bash/Git Bash/WSL), or manually: `docker compose exec ollama ollama pull <model>` |
| Backend deps | `cd api && uv sync` |
| Backend dev server | `cd api && uv run fastapi dev main.py` |
| Backend tests | `cd api && uv run pytest -q` (offline; fake Ollama transport; DB tests start an embedded Postgres via `pgserver`, or use `TEST_DATABASE_URL`) |
| Real-Ollama smoke test | `cd api && uv run pytest -m ollama` (needs Ollama at `LLM_BASE_URL` with `LLM_MODEL` + `EMBED_MODEL` pulled; skipped by default) |
| DB migrations | `cd api && uv run alembic upgrade head` (uses `DATABASE_URL`; from the host, use `postgresql://tenderly:tenderly@localhost:5432/tenderly`). The api container runs this on start. New migration: `uv run alembic revision --autogenerate -m "..."` |
| Seed demo company | `cd api && uv run python -m scripts.seed_demo` (needs migrated DB + Ollama with `bge-m3`; idempotent; exits 1 if any doc is not `ready`). Rebuild its DOCX/PDFs: `uv run python -m scripts.build_demo_docs`. With the Docker stack up: `docker compose exec api python -m scripts.seed_demo --data-dir /data/demo_company` (`data/demo_company` is mounted read-only; in Git Bash prefix `MSYS_NO_PATHCONV=1`). Use this when a native Postgres also holds host port 5432 |
| Seed tenders | With the API running: `curl -X POST localhost:8000/tenders/scrape` (37 synthetic notices, idempotent, offline). Live scraper (slow, ≥10 s per request, mostly scanned PDFs): `curl -X POST localhost:8000/tenders/scrape -H "content-type: application/json" -d '{"source":"kankai","max_notices":3}'` |
| Seed/scraper tests | `cd api && uv run pytest -q tests/test_seed_tenders.py tests/test_scraper.py tests/test_tenders_scrape_api.py` |
| Scout dev CLI | `cd api && uv run python -m api.agents.scout --seed` (`-m agents.scout` is the same module; needs Ollama; prints a field table; `--only 001,005`, `--json out.json`, `--db` to upsert into `DATABASE_URL` and write tenders + agent_runs rows; exits 1 if any notice failed) |
| Scout golden-set score | `cd api && uv run python -m api.scripts.score_scout [--manifest] [--out report.json]` (runs Scout on the real model; `--predictions out.json` scores saved CLI output offline). Labels: `data/golden/scout_expected.json` |
| Matching metric | `cd api && uv run python -m api.scripts.score_matching [--llm] [--records scout.json] [--out report.json]` (top-3 precision vs `data/golden/match_relevance.json` at its fixed clock; default = oracle records from the manifest + deterministic signals only, offline; `--llm` adds the real model's semantic score) |
| Matching tests | `cd api && uv run pytest -q tests/test_matching.py tests/test_tenders_list_api.py` |
| Scout tests | `cd api && uv run pytest -q tests/test_scout.py tests/test_nepal_scout_parsers.py` |
| Orchestrator / runs tests | `cd api && uv run pytest -q tests/test_orchestrator.py tests/test_runs_api.py tests/test_precache.py` |
| Analyze a tender (background run) | `curl -X POST localhost:8000/tenders/<id>/analyze` (202 + run; optional body `{"target":"checked","from_stage":"scout"}`), then poll `curl localhost:8000/runs/<run_id>`; list `curl localhost:8000/runs` |
| Pre-cache demo analyses | `cd api && uv run python -m api.scripts.precache_demo --seed-company` (fresh DB + Ollama; runs 001/002/003 Scout→Compliance and records `data/demo_cache/llm_cache.json`; `--only 001,005`, `--cache PATH`). Verify offline: `... precache_demo --check` (refuses all HTTP; exit 1 on any cache miss) |
| Compliance metric | `cd api && uv run python -m api.scripts.score_compliance [--llm] [--records scout.json] [--out report.json]` (recall + hard-fail recall on `data/golden/compliance_requirements.json`; default rules only, offline; `--llm` needs Ollama, uses an in-memory demo KB) |
| Compliance tests | `cd api && uv run pytest -q tests/test_compliance.py tests/test_compliance_api.py tests/test_nepal_rules.py` |
| Reference API tests | `cd api && uv run pytest -q tests/test_reference_api.py` |
| Frontend deps | `cd web && bun install` |
| Frontend dev server | `cd web && bun run dev` (needs the API on :8000), or without a backend: `NEXT_PUBLIC_USE_MOCKS=1 bun run dev` (bash) / `$env:NEXT_PUBLIC_USE_MOCKS='1'; bun run dev` (PowerShell) |
| Frontend tests | `cd web && bun run test` (Vitest, happy-dom, offline) |
| Frontend type-check / lint | `cd web && bunx tsc --noEmit` and `bun run lint`. `bun run build` fails on machines without Node (PROGRESS issue 25/56) |
| Add a shadcn component | `cd web && bunx --bun shadcn@latest add <name>` |
| Add the dialog component | `cd web && bunx --bun shadcn@latest add dialog` |
| Re-export BS calendar for the web | `cd api && uv run python -m api.scripts.export_bs_calendar` (writes `web/lib/nepal/bs-calendar.json`; `tests/test_bs_calendar_export.py` fails on drift) |
| E2E test | *_(TBD - Playwright not set up yet)_* |
| Regenerate API types | `cd web && bun run gen:api` (needs the API running locally on :8000, e.g. `cd api && uv run uvicorn main:app --port 8000`). Schemas only appear in the TS types if a route uses them as a request or response model. |
| Nepal layer tests | `cd api && uv run pytest -q tests/test_nepal_numbers.py tests/test_nepal_dates.py tests/test_nepal_geography.py tests/test_nepal_rules.py tests/test_nepal_scout_parsers.py` |
