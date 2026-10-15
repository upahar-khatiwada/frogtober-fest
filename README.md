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

## Running the pieces outside Docker

```bash
# Backend
cd api
uv sync
uv run fastapi dev main.py

# Frontend
cd web
bun install
bun run dev
```

See the [Commands table in `CLAUDE.md`](CLAUDE.md#commands) for the full
list (tests, DB migrations, API type generation, etc.).

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