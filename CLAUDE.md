# Tenderly

## Project summary

Tenderly is an agentic tender-to-proposal platform for Nepali SMEs. It scouts public tender notices, extracts them into structured records, scores each against a company profile, checks eligibility and compliance against the company's knowledge base, drafts a proposal grounded in that knowledge base, reviews the draft, and produces a submission-ready package after a human approves it. The pipeline is `Scout → Match → Compliance → Proposal → Review → Human approval → Package`. Each stage emits typed JSON that code consumes to route, filter, block or gate the next stage. For example, a low match score skips the tender, and a hard compliance failure blocks proposal generation.

The scope is set by a two-week, three-person build (Frogtoberfest). In scope: one live portal scraper plus a seeded dataset of 30–40 tenders, matching, compliance checking, RAG proposal generation, automated review, human approval, and DOCX/PDF package export, with an audit log of every agent run. Out of scope: automated portal submission, multi-tenant billing and accounts, OCR, multi-portal support, notifications, payments, and fine-tuning. The full spec is [docs/Tenderly_spec.pdf](docs/Tenderly_spec.pdf). Nepal-specific procurement facts are in [docs/NEPAL_CONTEXT.md](docs/NEPAL_CONTEXT.md).

**Demo claim:** "From a raw tender notice to a compliance-checked, reviewed proposal package in minutes, with a human approving every critical step."

## Hard rules

1. **Open-weight models only.** Serve them with Ollama. The LLM is `Qwen2.5-7B-Instruct` (fallback: Llama 3.1 8B) and the embedding model is `bge-m3` (1024 dimensions, fixed once chosen). The endpoint comes from the `LLM_BASE_URL` / `LLM_MODEL` env vars, and any hosted fallback must serve open-weight models only.
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
    ingest/            # scraper.py, parse_docs.py, embed.py
    export/            # docx.py, pdf.py, package.py
    tests/
  docker-compose.yml
  README.md ARCHITECTURE.md AI_DISCLOSURE.md LICENSE
```

Tender status state machine: `new → extracted → matched → checked → drafted → reviewed → approved`, with the branches `skipped` (score below threshold), `blocked` (hard compliance failure) and `failed` (a stage's LLM output was invalid after one retry).

## Contract layer

- **Schemas:** `api/schemas/`, one module per stage (`tender.py`, `match.py`, `compliance.py`, `proposal.py`, `review.py`), plus `company.py`, `runs.py` (agent_runs record), `views.py` (API response shapes), `enums.py` (all enums, Nepal ones documented in [docs/NEPAL_CONTEXT.md](docs/NEPAL_CONTEXT.md) §11) and `_base.py` (the `Contract` base with `extra="forbid"`, `FiscalYearBS`, `BSDateISO`). Import from `schemas`.
- **The LLM fills only these models:** `TenderRecord`, `MatchAssessment`, `ComplianceAssessment`, `ProposalSection`, `ReviewReport`. Code derives the rest: `MatchResult.from_assessment(a, threshold)` makes the pursue/skip decision, deterministic rules add `ComplianceItem`s with `rule_id`, and `ComplianceReport.is_blocked` does the gating.
- **LLM client:** `pipeline.llm.LLMClient(run_recorder, settings=None, transport=None, timeout_s=None)`. `chat(stage=, messages=, schema=, tender_id=, temperature=)` returns a validated model or raises `LLMOutputError` / `LLMTransportError`, and always calls `run_recorder(AgentRunRecord)` exactly once. Temperature is fixed per stage (`STAGE_TEMPERATURE`), and only `proposal` may be overridden (≤0.7). `embed(texts)` returns `EMBED_DIM` (1024) vectors and writes no agent_runs row.
- **Tests:** use `httpx.MockTransport` (see `FakeOllama` in `api/tests/conftest.py`). Never hit a real model in the default suite.

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
| Backend tests | `cd api && uv run pytest -q` (offline; fake Ollama transport) |
| Real-Ollama smoke test | `cd api && uv run pytest -m ollama` (needs Ollama at `LLM_BASE_URL` with `LLM_MODEL` + `EMBED_MODEL` pulled; skipped by default) |
| DB migrations | _(TBD - Prompt 3)_ |
| Seed tenders | _(TBD - Prompt 3+)_ |
| Frontend deps | `cd web && bun install` |
| Frontend dev server | `cd web && bun run dev` |
| Frontend tests | `cd web && bun run test` |
| E2E test | _(TBD - Playwright not set up yet)_ |
| Regenerate API types | `cd web && bun run gen:api` (needs the API running locally on :8000, e.g. `cd api && uv run uvicorn main:app --port 8000`). Schemas only appear in the TS types if a route uses them as a request or response model. |