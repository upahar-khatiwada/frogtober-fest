# Tenderly

Agentic tender-to-proposal automation for Nepali SMEs. Tenderly scouts public
tender notices, extracts them into structured records, scores each against a
company profile, checks eligibility and compliance against the company's
knowledge base, drafts a proposal grounded in that knowledge base, reviews
the draft, and produces a submission-ready package after a human approves it.

```
Scout → Match → Compliance → Proposal → Review → Human approval → Package
```

**Demo claim:** From a raw tender notice to a compliance-checked, reviewed
proposal package in minutes, with a human approving every critical step.

Full spec: [`docs/Tenderly_spec.pdf`](docs/Tenderly_spec.pdf)
Nepal procurement reference: [`docs/NEPAL_CONTEXT.md`](docs/NEPAL_CONTEXT.md)
Project rules and layout: [`CLAUDE.md`](CLAUDE.md)

## Stack

Next.js + TypeScript + Tailwind + shadcn/ui (served with **Bun**) · FastAPI +
Pydantic on Python 3.11 (managed with **uv**) · PostgreSQL + pgvector ·
Ollama (Qwen2.5-7B-Instruct + bge-m3) · Docker Compose.

Every model call — chat and embeddings — is an **open-weight model served by
Ollama**. There are no proprietary/hosted model APIs anywhere in this
project.

## Quick start

Requirements: Docker + Docker Compose. (Bun and uv are only needed if you
want to run `web/` or `api/` outside their containers — see below.)

```bash
cp .env.example .env
docker compose up --build
```

On first run, pull the Ollama models (chat + embedding) in a separate
terminal once the `ollama` service is up:

```bash
./scripts/setup.sh
```

Then open:

- Web UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- API health check: http://localhost:8000/health

## All commands

Every command you can run, grouped by task. Commands are in bash (Git Bash,
WSL, macOS, Linux). Where PowerShell needs different syntax (environment
variables), both forms are shown. **JavaScript tooling is Bun only:** never
use `npm`, `npx`, `yarn`, `pnpm` or `node`. **Python is uv only.**

What each command needs:

| Tag | Needs |
|---|---|
| *offline* | Nothing running. No model, no network. |
| *API* | The backend running on http://localhost:8000. |
| *DB* | PostgreSQL + pgvector, migrated. |
| *Ollama* | Ollama with `qwen2.5:7b-instruct` and `bge-m3` pulled. |

### 1. One-time setup

```bash
cp .env.example .env                  # Compose settings (DB, Ollama, matching knobs)

cd api && uv sync && cd ..            # backend deps (Python 3.11, incl. dev deps)
cd web && bun install && cd ..        # frontend deps
```

### 2. Run everything with Docker

```bash
docker compose up --build             # first time, or after Dockerfile changes
docker compose up                     # afterwards
docker compose up -d                  # same, in the background
docker compose logs -f api            # follow one service's logs (web, api, db, ollama)
docker compose down                   # stop (add -v to also delete the database volume)
```

Pull the models once the `ollama` service is up (in a second terminal):

```bash
./scripts/setup.sh                                        # pulls LLM_MODEL + EMBED_MODEL
docker compose exec ollama ollama list                    # check what is pulled
docker compose exec ollama ollama pull qwen2.5:7b-instruct  # or pull one by hand
```

Then open:

- Web UI: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- API health check: http://localhost:8000/health

The api container runs the DB migrations on start. Compose publishes Postgres
on `localhost:5432` and Ollama on `localhost:11434`, so all the host commands
below can use the Compose services.

### 3. Run the pieces on the host (without Docker for web/api)

From the host, the database and Ollama URLs are `localhost`, not the Compose
service names in `.env`:

```bash
# bash
export DATABASE_URL=postgresql://tenderly:tenderly@localhost:5432/tenderly
export LLM_BASE_URL=http://localhost:11434
```

```powershell
# PowerShell
$env:DATABASE_URL = "postgresql://tenderly:tenderly@localhost:5432/tenderly"
$env:LLM_BASE_URL = "http://localhost:11434"
```

Start only the database and Ollama in Docker, then run the backend and frontend on the host:

```bash
docker compose up -d db ollama

# Backend (http://localhost:8000)
cd api
uv run alembic upgrade head           # DB: create/upgrade the schema
uv run fastapi dev main.py            # dev server with reload
# or: uv run uvicorn main:app --port 8000

# Frontend (http://localhost:3000), in another terminal
cd web
bun run dev
```

**Frontend without any backend (mock data).** *offline*. It uses 10 sample
tenders, the demo company and its KB documents, and shows an amber "Mock data"
banner:

```bash
cd web && NEXT_PUBLIC_USE_MOCKS=1 bun run dev        # bash
```

```powershell
cd web; $env:NEXT_PUBLIC_USE_MOCKS = '1'; bun run dev  # PowerShell
```

Other frontend settings: `NEXT_PUBLIC_API_URL` sets the API URL for the browser
(default `http://localhost:8000`), and `API_URL` sets the API URL for the Next.js
server (Compose sets `http://api:8000`). `NEXT_PUBLIC_*` values are baked in at
build time.

### 4. Load the demo data

With the full Docker stack running, seed the demo company inside the api container.
Analyze returns "no company profile" until you do:

```bash
docker compose exec api python -m scripts.seed_demo --data-dir /data/demo_company
```

If a native Postgres also listens on port 5432 (common on Windows), `localhost:5432`
from the host reaches it instead of the Compose `db`, and a host-side seed fails with
"password authentication failed". Use the in-container command above.

From the host:

```bash
cd api

# Demo company: profile + 6 KB documents, parsed, chunked and embedded. DB + Ollama (bge-m3).
# Idempotent; exits 1 if any document is not "ready".
uv run python -m scripts.seed_demo
uv run python -m scripts.seed_demo --database-url postgresql://tenderly:tenderly@localhost:5432/tenderly

# Rebuild the demo company's DOCX/PDF files from source. offline
uv run python -m scripts.build_demo_docs
```

```bash
# 37 synthetic tender notices (raw text only; Scout extracts them later). API, offline, idempotent
curl -X POST localhost:8000/tenders/scrape

# Live scraper (bonus source kankaimun.gov.np: slow, >= 10 s per request, mostly scanned PDFs). API + network
curl -X POST localhost:8000/tenders/scrape -H "content-type: application/json" \
     -d '{"source":"kankai","max_notices":3}'
```

In the web UI, the **Load tenders** button on the dashboard does the same as
the first `curl` above.

### 5. Try the API by hand (the demo flow)

All of these need the API. The Swagger UI at http://localhost:8000/docs runs
the same calls.

```bash
# Ranked tender list, with optional filters (combine freely)
curl "localhost:8000/tenders"
curl "localhost:8000/tenders?procurement_type=works&province=gandaki&min_score=60"
curl "localhost:8000/tenders?district=कास्की&deadline_within_days=14"   # Nepali or English district
curl "localhost:8000/tenders?decision=pursue&status=blocked&limit=10&offset=0"
#   other filters: method, buyer_level, language

# One tender: extracted record, match result, compliance report
curl localhost:8000/tenders/1

# Run the pipeline on a tender in the background (Scout -> Matching -> Compliance). Ollama
curl -X POST localhost:8000/tenders/1/analyze                     # returns 202 + a run id
curl -X POST localhost:8000/tenders/1/analyze -H "content-type: application/json" \
     -d '{"target":"checked","from_stage":"scout"}'               # re-run from a given stage

# Watch pipeline runs (the UI polls these every 2 s)
curl localhost:8000/runs
curl "localhost:8000/runs?tender_id=1&status=failed"
curl localhost:8000/runs/1                                        # stages, durations, agent_runs rows

# A named person accepts a blocked tender's hard failures (human override)
curl -X POST localhost:8000/tenders/1/compliance/override -H "content-type: application/json" \
     -d '{"overridden_by":"Your Name","reason":"Fresh tax clearance applied for"}'

# Proposal: returns 409 while the tender is blocked, 501 once allowed (the stage is not built yet)
curl -X POST localhost:8000/tenders/1/proposal

# Company profile and knowledge base
curl localhost:8000/company
curl -X POST localhost:8000/company -H "content-type: application/json" \
     -d @data/demo_company/profile.json
curl localhost:8000/company/documents
curl -X POST localhost:8000/company/documents \
     -F file=@data/demo_company/06_construction_licence.txt \
     -F doc_type=business_licence -F expires_on_bs=2084-03-32 -F fiscal_year_bs=2083/84
#   optional fields: expires_on (AD date), value_npr (integer NPR)
```

### 6. Agent CLIs and metrics

All of these run from `api/`. The `api.` module prefix works only from inside
`api/` (`-m agents.scout` and `-m api.agents.scout` are the same module).

```bash
cd api

# Scout: extract the seed notices and print a field table. Ollama
uv run python -m api.agents.scout --seed                   # all 37
uv run python -m api.agents.scout --seed --only 001,005    # a few
uv run python -m api.agents.scout --seed --json out.json   # save the predictions
uv run python -m api.agents.scout --seed --db              # also write tenders + agent_runs rows (DATABASE_URL)

# Scout golden-set accuracy (deadline, budget, documents)
uv run python -m api.scripts.score_scout --manifest --out ../data/golden/report.json   # Ollama
uv run python -m api.scripts.score_scout --predictions out.json                        # offline: score saved output

# Matching: top-3 precision against data/golden/match_relevance.json
uv run python -m api.scripts.score_matching                                    # offline, rules only
uv run python -m api.scripts.score_matching --llm --out ../data/golden/match_report.json   # Ollama
uv run python -m api.scripts.score_matching --records out.json --llm           # use real Scout output

# Compliance: recall and hard-fail recall against data/golden/compliance_requirements.json
uv run python -m api.scripts.score_compliance                                  # offline, rules only
uv run python -m api.scripts.score_compliance --llm --out ../data/golden/compliance_report.json   # Ollama
uv run python -m api.scripts.score_compliance --records out.json --llm

# Demo replay cache: record the model answers for seeds 001/002/003 (fresh DB + Ollama), then check offline
uv run python -m api.scripts.precache_demo --seed-company
uv run python -m api.scripts.precache_demo --only 001,005 --cache ../data/demo_cache/llm_cache.json
uv run python -m api.scripts.precache_demo --check          # no HTTP; exits 1 on any cache miss
```

To use the replay cache, set `LLM_REPLAY_CACHE` to the cache file
(`../data/demo_cache/llm_cache.json` from the host; Compose already points to it).

### 7. Tests and checks

```bash
# Backend: whole suite (offline; fake Ollama; DB tests start an embedded Postgres via pgserver)
cd api && uv run pytest -q
TEST_DATABASE_URL=postgresql://tenderly:tenderly@localhost:5432/tenderly_test uv run pytest -q   # use your own Postgres

# Real-model smoke tests (Ollama with both models; skipped by default)
cd api && uv run pytest -m ollama

# Backend: by area
cd api && uv run pytest -q tests/test_nepal_numbers.py tests/test_nepal_dates.py tests/test_nepal_geography.py tests/test_nepal_rules.py tests/test_nepal_scout_parsers.py
cd api && uv run pytest -q tests/test_scout.py tests/test_nepal_scout_parsers.py
cd api && uv run pytest -q tests/test_matching.py tests/test_tenders_list_api.py
cd api && uv run pytest -q tests/test_compliance.py tests/test_compliance_api.py tests/test_nepal_rules.py
cd api && uv run pytest -q tests/test_orchestrator.py tests/test_runs_api.py tests/test_precache.py
cd api && uv run pytest -q tests/test_seed_tenders.py tests/test_scraper.py tests/test_tenders_scrape_api.py
cd api && uv run pytest -q tests/test_bs_calendar_export.py

# Frontend (offline)
cd web && bun run test              # Vitest (formatting utilities, calendar, i18n, components)
cd web && bunx tsc --noEmit         # type-check
cd web && bun run lint              # ESLint
cd web && bun run build             # production build; fails on machines without Node (PROGRESS.md issue 25)
cd web && bun run start             # serve the production build on :3000
```

There is no end-to-end (Playwright) test yet.

### 8. Maintenance

```bash
# New DB migration after changing api/db/models.py (review the generated file by hand)
cd api && uv run alembic revision --autogenerate -m "describe the change"
cd api && uv run alembic upgrade head

# Regenerate the frontend's API types after changing API routes or schemas (needs the API on :8000)
cd web && bun run gen:api

# Re-export the BS calendar table the web app uses (keeps the UI's BS dates identical to the API's)
cd api && uv run python -m api.scripts.export_bs_calendar

# Add a shadcn/ui component
cd web && bunx --bun shadcn@latest add <component>
```

## Repository layout

```
Tenderly/
  web/                 # Next.js + TypeScript frontend
  api/                 # FastAPI backend (agents, pipeline, schemas, ingest, export)
  docs/                # Spec and Nepal procurement reference
  scripts/             # Setup helpers (e.g. pulling Ollama models)
  docker-compose.yml
```

See [`CLAUDE.md`](CLAUDE.md) for the full layout, hard rules (open-weight
models only, deterministic compliance checks, schema-constrained LLM output,
etc.) and the session protocol this project is developed under.

## Status

This is a work-in-progress hackathon build (Frogtoberfest, two-week scope).
See [`PROGRESS.md`](PROGRESS.md) for what's done, open `[VERIFY]` items, and
what's next. Known limitations are tracked in
[`ARCHITECTURE.md`](ARCHITECTURE.md) as they're decided.

## License

[MIT](LICENSE)