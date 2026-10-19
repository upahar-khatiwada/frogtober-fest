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

```
Tenderly/
  web/                 # Next.js + TypeScript
  api/
    main.py
    routers/           # tenders.py, company.py, proposals.py, runs.py
    agents/            # scout.py, matching.py, compliance.py, proposal.py, review.py
    pipeline/          # orchestrator.py (state machine), llm.py (Ollama client)
    schemas/           # Pydantic models shared by all stages
    ingest/            # parse_docs.py, chunking.py, embed.py, kb.py (upload -> parse -> chunk -> embed);
                       # notices.py (RawNotice + upsert), seed_tenders.py, scraper.py (live: kankaimun.gov.np)
    db/                # models.py (SQLAlchemy 2), session.py, search.py (pgvector top-k cosine), runs.py (agent_runs recorder)
    alembic/           # migrations (source of truth for the live schema); alembic.ini in api/
    scripts/           # seed_demo.py, build_demo_docs.py, score_scout.py (Scout golden-set scorer)
    deps.py            # FastAPI deps: get_session, get_sessionmaker, get_llm_client (tests override)
    api/__init__.py    # alias package only: makes `python -m api.<module>` work from api/ (app code imports flat names)
    export/            # docx.py, pdf.py, package.py
    tests/
  data/demo_company/  # FICTIONAL demo SME: profile.json, manifest.json, 5 KB documents
  data/seed_tenders/  # 37 SYNTHETIC tender notices (.txt) + manifest.json with labelled ground truth
  data/golden/        # scout_expected.json: Scout golden set (15 ids, 5 labelled)
  docker-compose.yml
  README.md ARCHITECTURE.md AI_DISCLOSURE.md LICENSE

- **Nepal layer:** `api/nepal/` (`numbers.py`, `dates.py`, `geography.py`, `documents.py`, `rules.yaml`, `rules.py`). Deterministic, no LLM. Rules evaluator: `nepal.rules.evaluate_rules(tender, company, documents, criteria=, now=)` returns `ComplianceItem`s with `rule_id` (criteria default to `tender.criteria`). Scout parsers: `parse_deadline(raw)` → `DeadlineParse` (BS/AD/time, `issues` instead of guesses), `parse_npr` (strict grouping, compound "32 lakh 50 thousand"), `parse_percent`, `parse_days`, `documents.classify_document` / `find_fiscal_years`. Import from `nepal`.
```

Tender status state machine: `new → extracted → matched → checked → drafted → reviewed → approved`, with the branches `skipped` (score below threshold), `blocked` (hard compliance failure) and `failed` (a stage's LLM output was invalid after one retry).

## Contract layer

- **Schemas:** `api/schemas/`, one module per stage (`tender.py`, `match.py`, `compliance.py`, `proposal.py`, `review.py`), plus `company.py`, `runs.py` (agent_runs record), `views.py` (API response shapes), `enums.py` (all enums, Nepal ones documented in [docs/NEPAL_CONTEXT.md](docs/NEPAL_CONTEXT.md) §11) and `_base.py` (the `Contract` base with `extra="forbid"`, `FiscalYearBS`, `BSDateISO`). Import from `schemas`.
- **The LLM fills only these models:** `TenderExtraction` (`schemas/scout.py`: verbatim `{value, quote}` strings, no conversions), `MatchAssessment`, `ComplianceAssessment`, `ProposalSection`, `ReviewReport`. Code derives the rest: `MatchResult.from_assessment(a, threshold)` makes the pursue/skip decision, deterministic rules add `ComplianceItem`s with `rule_id`, and `ComplianceReport.is_blocked` does the gating.
- **LLM client:** `pipeline.llm.LLMClient(run_recorder, settings=None, transport=None, timeout_s=None)`. `chat(stage=, messages=, schema=, tender_id=, temperature=)` returns a validated model or raises `LLMOutputError` / `LLMTransportError`, and always calls `run_recorder(AgentRunRecord)` exactly once. Temperature is fixed per stage (`STAGE_TEMPERATURE`), and only `proposal` may be overridden (≤0.7). `embed(texts)` returns `EMBED_DIM` (1024) vectors and writes no agent_runs row.
- **Database:** SQLAlchemy 2 models in `api/db/models.py` mirror spec §11 plus Nepal columns. Enum columns are TEXT with CHECK constraints from `schemas/enums.py`, so adding an enum value needs a migration. `tests/test_db.py::test_migration_matches_models` fails if models and migrations drift. Create migrations with `uv run alembic revision --autogenerate -m ...`, then review them by hand.
- **KB ingestion:** `POST /company/documents` stores the file and runs `ingest.kb.ingest_document` as a background task. The result lives in `documents.ingest_status` (`IngestStatus`: pending/processing/ready/needs_ocr/failed). Scanned PDFs become `needs_ocr` (no OCR). Chunks are 400–600 *estimated* tokens with 80 overlap (`ingest/chunking.py`). Retrieval goes through `db.search.search_chunks(session, vector, k, company_id=, doc_types=)` or `db.search.retrieve(session, client, query, k)`, and only `ready` documents are searched. Cite `ChunkHit.chunk_id`.
- **Tender ingestion:** `POST /tenders/scrape` (`ScrapeRequest`, default `{"source": "seed"}`) loads `data/seed_tenders/` (setting `SEED_TENDERS_DIR`; mounted read-only in Docker) or, with `"source": "kankai"`, runs the live scraper. Both produce `ingest.notices.RawNotice`s, and `upsert_notices` upserts them by `source_url` (seeds are `seed://seed_tenders/<file>`). New rows get status `new` and **raw text only**; Scout does all extraction. Identical text leaves a row (and its pipeline progress) untouched. Changed text resets it to `new`, clears derived columns and drops its match/compliance rows. The seed set is the demo source, and the scraper is a bonus that must never be a dependency (spec §17). The scraper enforces the robots, delay, UA and no-login rules in `ingest/scraper.py`'s docstring. Don't loosen them. Source findings are in NEPAL_CONTEXT §6. Scout is **not** enqueued from the endpoint yet.
- **Scout (`agents/scout.py`):** `extract_tender(client, raw_text, tender_id=)` = one LLM call (`TenderExtraction`) + `postprocess(extraction, raw_text)`, which is pure code. It builds the `TenderRecord` with the Nepal layer, checks every raw string and quote is in the notice (`Grounder`: tolerant only of whitespace, case, digit script and quote style), and stores `sources[]` (value, raw, quote, char span in `tenders.raw_text`) for value-next-to-source UI. If a raw string is not verbatim or does not parse, the value is null, a `ReviewFlag` is added and `needs_review` is true. Never guess. `language` is computed (Devanagari share), not asked of the LLM. `run_scout(session, client, tender)` / `scout_new_tenders` write the row and set `extracted` or `failed`. The agent_runs row keeps the raw LLM extraction; `record_json` keeps the derived record.
- **Tests:** use `httpx.MockTransport` (see `FakeOllama` in `api/tests/conftest.py`; `MockKankai` in `tests/test_scraper.py` serves saved HTML from `tests/fixtures/scraper/`). Never hit a real model or a real website in the default suite. Never hit a real model in the default suite. DB tests use `TEST_DATABASE_URL` if set, else an embedded Postgres+pgvector from the `pgserver` dev dependency (fixtures `session_factory` / `db_session` in conftest; tables are truncated per test). `bag_of_words_vector` is a deterministic fake embedder for retrieval tests.

## Session protocol

- **At the start of every task:** read `CLAUDE.md`, `PROGRESS.md` and `docs/NEPAL_CONTEXT.md`.
- **At the end of every task:** update `PROGRESS.md` (Done, Decisions, Deviations from spec, Open issues, Next prompt). Also update `CLAUDE.md` and/or `docs/NEPAL_CONTEXT.md` if anything they describe changed (commands, layout, rules, verified facts).
- Never overwrite these three files wholesale. Edit them in place.

## Commands

| Purpose | Command |
|---|---|
| Start full stack | `docker compose up --build` (first time / after Dockerfile changes), `docker compose up` after |
| Pull models | `./scripts/setup.sh` (bash/Git Bash/WSL), or manually: `docker compose exec ollama ollama pull <model>` |
| Backend deps | `cd api && uv sync` |
| Backend dev server | `cd api && uv run fastapi dev main.py` |
| Backend tests | `cd api && uv run pytest -q` (offline; fake Ollama transport; DB tests start an embedded Postgres via `pgserver`, or use `TEST_DATABASE_URL`) |
| Real-Ollama smoke test | `cd api && uv run pytest -m ollama` (needs Ollama at `LLM_BASE_URL` with `LLM_MODEL` + `EMBED_MODEL` pulled; skipped by default) |
| DB migrations | `cd api && uv run alembic upgrade head` (uses `DATABASE_URL`; from the host, use `postgresql://tenderly:tenderly@localhost:5432/tenderly`). The api container runs this on start. New migration: `uv run alembic revision --autogenerate -m "..."` |
| Seed demo company | `cd api && uv run python -m scripts.seed_demo` (needs migrated DB + Ollama with `bge-m3`; idempotent; exits 1 if any doc is not `ready`). Rebuild its DOCX/PDFs: `uv run python -m scripts.build_demo_docs` |
| Seed tenders | With the API running: `curl -X POST localhost:8000/tenders/scrape` (37 synthetic notices, idempotent, offline). Live scraper (slow, ≥10 s per request, mostly scanned PDFs): `curl -X POST localhost:8000/tenders/scrape -H "content-type: application/json" -d '{"source":"kankai","max_notices":3}'` |
| Seed/scraper tests | `cd api && uv run pytest -q tests/test_seed_tenders.py tests/test_scraper.py tests/test_tenders_scrape_api.py` |
| Scout dev CLI | `cd api && uv run python -m api.agents.scout --seed` (`-m agents.scout` is the same module; needs Ollama; prints a field table; `--only 001,005`, `--json out.json`, `--db` to upsert into `DATABASE_URL` and write tenders + agent_runs rows; exits 1 if any notice failed) |
| Scout golden-set score | `cd api && uv run python -m api.scripts.score_scout [--manifest] [--out report.json]` (runs Scout on the real model; `--predictions out.json` scores saved CLI output offline). Labels: `data/golden/scout_expected.json` |
| Scout tests | `cd api && uv run pytest -q tests/test_scout.py tests/test_nepal_scout_parsers.py` |
| Frontend deps | `cd web && bun install` |
| Frontend dev server | `cd web && bun run dev` |
| Frontend tests | `cd web && bun run test` |
| E2E test | _(TBD - Playwright not set up yet)_ |
| Regenerate API types | `cd web && bun run gen:api` (needs the API running locally on :8000, e.g. `cd api && uv run uvicorn main:app --port 8000`). Schemas only appear in the TS types if a route uses them as a request or response model. |
| Nepal layer tests | `cd api && uv run pytest -q tests/test_nepal_numbers.py tests/test_nepal_dates.py tests/test_nepal_geography.py tests/test_nepal_rules.py tests/test_nepal_scout_parsers.py` |