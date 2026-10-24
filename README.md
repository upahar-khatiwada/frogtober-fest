# Tenderly

Agentic tender-to-proposal automation for Nepali SMEs. Tenderly scouts public
tender notices, extracts them into structured records, scores each against a
company profile, checks eligibility and compliance against the company's
knowledge base, drafts a proposal grounded in that knowledge base, reviews
the draft, and produces a submission-ready package after a human approves it.
**Nothing is ever submitted to a portal.** A person uploads the package.

**Demo claim:** From a raw tender notice to a compliance-checked, reviewed
proposal package in minutes, with a human approving every critical step.

- Spec: [`docs/Tenderly_spec.pdf`](docs/Tenderly_spec.pdf)
- Architecture and agent contracts: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Where AI output is consumed by code, and what is code vs model: [`AI_DISCLOSURE.md`](AI_DISCLOSURE.md)
- Demo script, pitch and video script: [`docs/DEMO.md`](docs/DEMO.md)
- Nepal procurement reference: [`docs/NEPAL_CONTEXT.md`](docs/NEPAL_CONTEXT.md)
- Evaluation: [`docs/EVAL.md`](docs/EVAL.md) · Project rules: [`CLAUDE.md`](CLAUDE.md) · Build log: [`PROGRESS.md`](PROGRESS.md)

## The problem

> _An illustration. The company, the notice and the numbers are the synthetic ones in `data/`._
>
> A class-C construction firm in Pokhara finds a municipal notice for gravelling and drains in Tanahun
> (Rs 1,48,75,000, deadline 2083-08-05 BS). It fits the firm's work, district and size, and the firm has done
> bigger jobs. Two days before the deadline the engineer assembles the bid. The notice asks for a tax clearance
> for **F/Y 2082/83**. The firm's clearance on file is for F/Y 2081/82, and expired on 2083-03-32 BS
> (16 July 2026). The bid is submitted anyway. Under Public Procurement Rules Rule 40(4), a bid missing the
> eligibility documents "shall not be entertained", so it is rejected unread, along with the Rs 4,46,000 bid
> security the firm had arranged.

Small contractors lose bids in four ways: finding the notices (scattered, updated daily), triage (long
documents in two scripts and two calendars), compliance (one expired or missing certificate, or a bid
security that lapses before the bid validity ends, disqualifies a bid), and proposal effort (the same
company facts retyped for every bid under deadline pressure).

## The solution

A pipeline of stages. Each stage emits typed JSON that code consumes to route, filter, block or gate the
next stage.

```mermaid
flowchart LR
    N[Notice: seed set or live scrape] --> S[Scout<br/>extract]
    S --> M[Matching<br/>score + rank]
    M -- "score below threshold" --> SK[skipped]
    M -- pursue --> C[Compliance<br/>rules + KB evidence]
    C -- "hard failure" --> B[blocked]
    B -. "named human override" .-> C2[checked]
    C -- ok --> C2
    C2 --> P[Proposal<br/>RAG, cited sections]
    P --> R[Review<br/>checks + scores]
    R -- "needs work (once)" --> P
    R --> H{{Human approval}}
    H --> K[Package<br/>PDF + DOCX + checklist + audit]
    KB[(Company KB<br/>pgvector)] -.-> M
    KB -.-> C
    KB -.-> P
```

What the pipeline changes in the system's behaviour: a low match score means Compliance never runs; a hard
compliance failure means no proposal can be generated (409) until a named person overrides it; a failed hard
review check means the proposal cannot be approved; only an approval produces a package. The model never
makes these decisions. See [`AI_DISCLOSURE.md`](AI_DISCLOSURE.md) for the split.

## Quick start

Requirements: Docker + Docker Compose. An NVIDIA GPU is strongly recommended: on CPU a 7B model is too
slow and Scout calls hit the 180 s timeout. Bun and uv are only needed to run `web/` or `api/` outside
Docker.

```bash
cp .env.example .env
docker compose up --build                  # NVIDIA GPU: add -f docker-compose.yml -f docker-compose.gpu.yml
./scripts/setup.sh                         # in a second terminal: pulls qwen2.5:7b-instruct and bge-m3
docker compose exec api python -m scripts.seed_demo --data-dir /data/demo_company   # demo company + 6 KB documents
curl -X POST localhost:8000/tenders/scrape                                          # 37 synthetic notices (offline)
```

Then open http://localhost:3000 (API docs: http://localhost:8000/docs). On Windows without Git Bash,
pull the models with `docker compose exec ollama ollama pull qwen2.5:7b-instruct` and `... pull bge-m3`.

**Local web development (Bun).** The frontend can run without Docker and even without a backend:

```bash
cd web && bun install
bun run dev                                       # needs the API on :8000
NEXT_PUBLIC_USE_MOCKS=1 bun run dev               # no backend: sample data, shows a "Mock data" banner
# PowerShell: $env:NEXT_PUBLIC_USE_MOCKS='1'; bun run dev
```

JavaScript tooling is Bun only (never `npm`, `npx`, `yarn`, `pnpm`); Python is `uv` only. The full command
reference is under [All commands](#all-commands).

## Demo

The rehearsed path uses one fictional company and three prepared notices (one strong match, one blocked by
compliance on the expired tax clearance, one skipped as irrelevant). The script, who talks and who drives
the screen, the 5-minute pitch, the 3-minute video script and prepared answers are in
[`docs/DEMO.md`](docs/DEMO.md). The fully scripted path is also the single Playwright test
(`web/e2e/demo.spec.mjs`).

## Models and dependencies

**Models (all open weights, served by Ollama; the endpoint comes from `LLM_BASE_URL` / `LLM_MODEL`):**

| Use                                                  | Model                 | Notes                                                                                 |
| ---------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------- |
| Chat (Scout, Matching, Compliance, Proposal, Review) | `qwen2.5:7b-instruct` | Qwen2.5-7B-Instruct. Fallback: Llama 3.1 8B. JSON-schema constrained, `num_ctx` 8192. |
| Embeddings                                           | `bge-m3`              | Multilingual (English + Nepali), 1024 dimensions, fixed in migration `0001`.          |

**Backend (Python 3.11, uv):** FastAPI, Pydantic 2 and pydantic-settings, httpx (used only in `api/pipeline/llm.py`
for models and in `api/ingest/scraper.py` for the scraper), SQLAlchemy 2 + Alembic + psycopg, pgvector,
PyMuPDF, python-docx, BeautifulSoup, `nepali-datetime` (BS calendar), PyYAML, ReportLab + uharfbuzz (PDF with
Devanagari shaping), python-multipart. Dev: pytest, `pgserver` (embedded Postgres + pgvector for tests).
**Frontend (Bun):** Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui (base-ui), `openapi-fetch` +
`openapi-typescript`, lucide-react. Dev: Vitest + happy-dom, Testing Library, Playwright.
**Infrastructure:** PostgreSQL 16 with pgvector (`pgvector/pgvector:pg16`), Ollama, Docker Compose.
**Bundled fonts:** Noto Sans and Noto Sans Devanagari (SIL OFL, embedded in the PDF export).

None of these calls a proprietary service. `api/tests/test_no_proprietary.py` fails the build on a
proprietary SDK, an API key, a hosted default, or a model call outside `api/pipeline/llm.py`.

### Open-weight models only

Every model call, chat and embedding, uses an open-weight model through one client (`api/pipeline/llm.py`).
There are no proprietary hosted APIs anywhere, including library default embeddings. If no GPU is available,
`LLM_BASE_URL` and `LLM_MODEL` may point at a hosted inference provider, **but only one that serves
open-weight models.** Changing the embedding model needs a new migration and a full re-embed.

## Nepal-specific features

- **Bikram Sambat (BS) calendar.** Deadlines, expiry dates and fiscal years are handled in BS and AD
  (`api/nepal/dates.py`, using the `nepali-datetime` lookup table, never arithmetic and never the model).
  Notices that print BS, AD, both, Devanagari digits or `HH:MM`/"बजे"/"noon" are parsed deterministically;
  a date-only deadline is end of day NPT (UTC+05:45); the fiscal year starts on Shrawan 1. A BS/AD
  mismatch inside one notice is flagged, not guessed. The web app uses a calendar table **exported from the
  backend** (`api/scripts/export_bs_calendar.py`, drift-tested) so the UI and API never disagree, and has a
  BS/AD toggle everywhere.
- **Bilingual support.** The UI is fully English and Nepali (`web/lib/i18n/dict.ts`, same keys enforced by a
  test). Notices may be English, Nepali or mixed; Scout copies Devanagari verbatim, digits and `रु.`/lakh/crore
  amounts are normalised in code, and districts match in either script. Proposals are drafted in Nepali for
  Nepali and mixed notices (English on request). The PDF export shapes Devanagari with HarfBuzz and embeds
  Noto Sans Devanagari, and extracts back to the same Unicode (tested on all 24 Devanagari seed notices).
- **Rules engine.** `api/nepal/rules.yaml` + `rules.py` hold 14 deterministic compliance rules (deadline,
  registration and licence, PAN/VAT, tax clearance for the notice's fiscal year, licence renewal, turnover,
  experience, bid and performance security, JV, domestic preference, document validity over the bid validity
  period, other mandatory documents). Each rule has a severity, a source and a `verified` flag; the five
  rules that are not verified against current law are marked `verified: false` and shown as unverified in
  the UI (see [Limitations](#limitations)). Thresholds come from the notice, never from statute.
- **Bid security calculator.** `calc_bid_security` returns the amount (the notice's fixed amount, or the
  notice's own percentage rounded up) and the valid-until date in BS and AD, from the notice only. The
  Compliance matrix and the checklist tell the bidder what guarantee to arrange.
- **Nepal-style bid package.** The approved proposal exports as a ZIP: a cover letter with the procuring
  entity and subject line, a bid-form skeleton with blank price and signatory (the bidding document's form
  remains the authority), the declarations under PPR Rule 40(2)(e), the technical proposal with KB
  citations, an attachment checklist that marks each required document present, expiring or missing (with
  expiry in BS and AD), the KB originals, a CSV of the checklist and a JSON audit summary
  (`submitted: false`). Details: [`docs/NEPAL_CONTEXT.md`](docs/NEPAL_CONTEXT.md) §16.

## Evaluation (honest numbers)

Full detail and how to read them: [`docs/EVAL.md`](docs/EVAL.md). Regenerate with
`cd api && uv run python -m api.eval`.

**No model-in-the-loop number has been measured yet.** There was no Ollama on the development machine, so
every row that needs the real model is `n/a`, not guessed. What exists is the deterministic (code-only) layer
measured offline, on hand-labelled **synthetic** data:

| Metric                                                     | Result           | What it measures                                                                                                 |
| ---------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| Matching: relevant tenders in the top 3                    | 100% (3/3)       | Deterministic signals only, oracle records.                                                                      |
| Matching: core (best) tenders in the top 3                 | **33.3%** (1/3)  | The code-only floor. All in-scope tenders tie at 100 deterministic points, so their ordering is the model's job. |
| Matching: relevant tenders pursued                         | 100% (11/11)     |                                                                                                                  |
| Matching: irrelevant tenders skipped                       | 92.3% (24/26)    | The 2 misses (007 corrigendum, 037 cancellation) need the model.                                                 |
| Compliance: mandatory requirements covered                 | 100% (54/54)     | Some item exists for each labelled requirement.                                                                  |
| Compliance: hard-fail recall (worst error)                 | **81.8%** (9/11) | Misses `002:licence_class` and `002:key_equipment`, which only the model layer can fail. This is the floor.      |
| Compliance: status accuracy                                | 66.7% (36/54)    | Conservative `unclear`s, not wrong passes.                                                                       |
| Compliance: false hard fails                               | 0                |                                                                                                                  |
| Compliance: blocked / not-blocked accuracy                 | 100% (7/7)       |                                                                                                                  |
| Scout: deadline, budget, required documents                | **not run**      | Needs the model. Ceiling of the code half: a hand-written ideal extraction of 001 scores 100%.                   |
| Proposal: sections with a valid KB citation                | **not run**      | Needs the model. Fake-model tests only prove the grounding code.                                                 |
| Review and model-layer Compliance, Matching semantic score | **not run**      | Same.                                                                                                            |

Caveats: the 37 notices and the demo company are synthetic and the labels were written by the team from the
same text, so these numbers show the plumbing and the code-only floor, not accuracy on real notices. The
Scout golden set has 15 notices, 5 fully labelled and 10 with deadline and budget labels only. A 7B model
will make mistakes the code is built to catch (it flags a value the notice does not contain instead of
guessing) but their rate is **unmeasured**.

**Test suites** (run on 2026-10-24): backend `uv run pytest -q` gives **746 passed**, 4 deselected (real-Ollama
smoke tests, run with `-m ollama`); frontend `bun run test` gives **97 passed** (Vitest); the one Playwright
test passes against mock data (`E2E_MOCKS=1`) and has **not** been run against the live stack.

## Limitations

- **No automated submission.** The final upload is manual, by design.
- **One live source.** The live scraper reads one municipal notice board (kankaimun.gov.np); the national
  portal blocks non-browser clients and is not scraped. The 37 synthetic seed notices are the demo source.
- **No OCR.** Scanned PDFs are marked `needs_ocr` and skipped. Both live notices seen on 2026-10-19 were
  scans, so the live scraper yields little today.
- **Small-model errors.** A 7B model can misread complex clauses. Extraction is grounded in code (values
  not found verbatim in the notice become null and are flagged `needs_review`), compliance evidence without a
  KB chunk is `unclear`, never `pass`, and a person approves every proposal.
- **Rules marked unverified in `rules.yaml`.** NP-LICENCE-RENEWAL, NP-TURNOVER, NP-EXPERIENCE,
  NP-DOMESTIC-PREF and NP-DOC-VALIDITY are `verified: false`. The English Rules text available to the team
  is the 2008 version, and current thresholds are `[VERIFY]` in `docs/NEPAL_CONTEXT.md` §10. Tenderly reads
  amounts and validity from each notice, not from law.
- **English-first generation quality.** Qwen2.5-7B writes better English than Nepali. Nepali notices get
  Nepali proposals by default, which is the weakest output, and the UI labels were not reviewed by a native
  speaker.
- **Single tenant.** One company, no authentication, no accounts.
- **Not yet verified end to end.** The demo replay cache is not recorded, no completed run against the real
  model is recorded (the one attempt, Scout on CPU, timed out; it has not been repeated on the GPU), and
  `bun run build` fails on a machine without Node (the Docker build is the check). See
  [`PROGRESS.md`](PROGRESS.md).

**Future work:** browser-driven assisted submission with a human confirmation at every irreversible
step; more portals through a plug-in scraper interface; OCR and layout-aware parsing for scanned
tenders; a fine-tuned Nepali extraction model; multi-user workspaces, deadline alerts, and win/loss
feedback to improve matching.

## All commands

Every command you can run, grouped by task. Commands are in bash (Git Bash,
WSL, macOS, Linux). Where PowerShell needs different syntax (environment
variables), both forms are shown. **JavaScript tooling is Bun only:** never
use `npm`, `npx`, `yarn`, `pnpm` or `node`. **Python is uv only.**

What each command needs:

| Tag       | Needs                                                  |
| --------- | ------------------------------------------------------ |
| _offline_ | Nothing running. No model, no network.                 |
| _API_     | The backend running on http://localhost:8000.          |
| _DB_      | PostgreSQL + pgvector, migrated.                       |
| _Ollama_  | Ollama with `qwen2.5:7b-instruct` and `bge-m3` pulled. |

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

**NVIDIA GPU (strongly recommended).** By default Ollama runs on the CPU: about 25
prompt tokens/s, so Scout calls time out (`/api/chat timed out after 180.0s`). Add the
GPU override:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
docker compose exec ollama ollama ps        # PROCESSOR should say "100% GPU"
```

To make it the default, put `COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml` in `.env`
(use `;` on Windows and `:` on Linux/macOS). Then plain `docker compose up` picks it up.

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

**Frontend without any backend (mock data).** _offline_. It uses 10 sample
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

# Proposal + Review (background run, 202). 409 while the tender is blocked; then poll the run
curl -X POST localhost:8000/tenders/1/proposal
curl localhost:8000/tenders/1/proposals

# Human gate: open, approve (needs a reviewed version that was opened after its review), download the package
curl -X POST localhost:8000/proposals/1/open
curl -X POST localhost:8000/proposals/1/approve -H "content-type: application/json" -d '{"approved_by":"Your Name"}'
curl -o package.zip localhost:8000/proposals/1/package

# Audit log of every agent run (model, code and human rows)
curl "localhost:8000/agent-runs?tender_id=1"

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
cd api && uv run pytest -q tests/test_proposal.py
cd api && uv run pytest -q tests/test_review.py tests/test_proposal_page_api.py
cd api && uv run pytest -q tests/test_export.py          # incl. Devanagari PDF round trips
cd api && uv run pytest -q tests/test_failure_drills.py tests/test_no_proprietary.py
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

There is one end-to-end (Playwright) test, `web/e2e/demo.spec.mjs`:

```bash
cd web && bunx playwright install chromium            # once
cd web && E2E_MOCKS=1 bunx playwright test            # against mocks, no backend (PowerShell: $env:E2E_MOCKS='1')
cd web && bunx playwright test                        # real stack with the pre-cached demo (see docs/DEMO.md)

# Full evaluation: every metric into docs/EVAL.md (Ollama unless --offline)
cd api && uv run python -m api.eval --offline
```

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
  web/                 # Next.js + TypeScript frontend (pages: /, /company, /runs, /tenders/[id], /tenders/[id]/proposal)
  api/                 # FastAPI backend: agents/, pipeline/, nepal/ (rules engine), schemas/, ingest/, export/, db/, routers/, tests/
  data/                # demo_company/ (fictional), seed_tenders/ (37 synthetic), golden/ (labels), demo_cache/
  docs/                # Spec, Nepal procurement reference, evaluation, demo script
  scripts/             # Setup helpers (pulling Ollama models)
  docker-compose.yml   # web, api, db (pgvector), ollama (+ docker-compose.gpu.yml)
```

See [`CLAUDE.md`](CLAUDE.md) for the full layout, hard rules and conventions, and
[`ARCHITECTURE.md`](ARCHITECTURE.md) for how the pieces fit.

## Status

v1.0 of a two-week hackathon build (Frogtoberfest). Everything in the spec's MVP path is implemented and
covered by offline tests. What is not yet verified, and the remaining gaps, are listed in
[`PROGRESS.md`](PROGRESS.md) and above under [Limitations](#limitations).

## License

[MIT](LICENSE)
