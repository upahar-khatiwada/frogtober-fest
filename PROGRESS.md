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

## Deviations from spec
- None in behaviour. Additive fields beyond §8.1/§11: `TenderStatus.failed`, `AgentRunRecord.attempts/error/raw_output` (the `agent_runs` table needs these three columns when migrations land), `ReviewGap.severity`, `ComplianceItem.explanation`. (The spec allowed bge-m3 *or* nomic-embed-text; choosing bge-m3 is a selection within the spec.)

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

Other:
- The spec's AI-disclosure table (§15.1) is garbled in the PDF text extraction. Function names will be finalised from real code.

## Next prompt
Prompt 3: database + Scout. Add migrations for spec §11 (plus the `agent_runs.attempts/error/raw_output` columns and `tenders.status` values from `TenderStatus`), and a `run_recorder` that inserts `agent_runs` rows. Build the deterministic normalisers (Devanagari digits, Rs/NRs/रु., lakh/crore/million, BS date → `deadline_bs_iso`, BS→AD via a vetted library), then the Scout agent (`LLMClient.chat(stage=SCOUT, schema=TenderRecord)` + normalisers overwriting code-owned fields) and the seed dataset loader. Resolve open issues 12/13 first if possible.

