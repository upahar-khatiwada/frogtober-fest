"""Pre-cache the demo analyses so the pitch works even if the model is slow (spec sections 10.5, 17).

Runs the full pipeline (Scout -> Matching -> Compliance) on the demo seed tenders with a *recording*
LLM client. Results land in the DB as usual (tenders, matches, compliance_items, pipeline_runs,
agent_runs), and every validated model output and embedding is saved to the replay cache file. Point
the API at that file (LLM_REPLAY_CACHE) and the same requests are answered from it in milliseconds:
outputs are still schema-validated, deterministic code still runs, and each agent_runs row says
`cached`. A request the cache does not hold (a changed prompt or KB) falls through to the live model.

Cache keys include the prompt, and prompts cite KB chunk ids, so record on the same KB the demo uses:
best on a fresh DB with `--seed-company` (chunk ids then start at 1, as after any fresh `seed_demo`).

    cd api && uv run python -m api.scripts.precache_demo [--only 001,002,003] [--cache PATH] [--seed-company]
    cd api && uv run python -m api.scripts.precache_demo --check   # replay only, no HTTP: exits 1 on any miss
    cd api && uv run python -m api.scripts.precache_demo --seed-company --through-review 001 --now 2026-10-22T10:00:00+05:45

`--through-review` carries those seeds on to a reviewed proposal (Proposal + Review, incl. Review's one revision), so
the whole demo path (and the Playwright E2E test) replays offline. A blocked seed is overridden first, as the
presenter does on stage; the override is not part of any prompt. Proposal text carries today's date and Review reads
it, so record with `--now` and serve the API with the same `DEMO_NOW`, or Review misses on another day.

Needs a migrated DB, and (unless --check) Ollama with LLM_MODEL and EMBED_MODEL pulled.
"""

import argparse
import sys
from pathlib import Path

import httpx
from sqlalchemy.orm import sessionmaker

from datetime import datetime

from agents.compliance import override_block
from agents.matching import load_company
from config import get_settings
from db.runs import make_run_recorder
from db.session import make_engine
from ingest.notices import upsert_notices
from ingest.seed_tenders import load_seed_notices
from pipeline.llm import LLMClient, ReplayCache
from pipeline.orchestrator import run_pipeline
from db.models import Tender
from nepal.dates import NPT
from schemas import IngestStatus, RunStatus, Stage, TenderStatus

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / "data" / "demo_cache" / "llm_cache.json"
DEMO_IDS = ("001", "002", "003")  # strong match, hard fail, irrelevant (data/seed_tenders/manifest.json roles)
OVERRIDDEN_BY = "Tenderly pre-cache"


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"--check: no live model calls ({request.url.path} not in the replay cache)")


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default=",".join(DEMO_IDS), help="comma-separated seed ids (default: 001,002,003)")
    parser.add_argument("--cache", type=Path, default=Path(settings.llm_replay_cache) if settings.llm_replay_cache else DEFAULT_CACHE)
    parser.add_argument("--seed-company", action="store_true", help="(re)seed the demo company first, caching its embeddings")
    parser.add_argument("--check", action="store_true", help="replay only: refuse all HTTP, exit 1 on any cache miss")
    parser.add_argument("--through-review", default="", help="comma-separated seed ids to carry on to a reviewed proposal")
    parser.add_argument("--now", type=datetime.fromisoformat, default=settings.demo_now,
                        help="pin the clock (ISO with offset); serve with the same DEMO_NOW. Default: DEMO_NOW or real time")
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--seed-dir", type=Path, default=settings.seed_tenders_dir)
    args = parser.parse_args(argv)

    if args.check and not args.cache.is_file():
        print(f"No replay cache at {args.cache}; run without --check first.")
        return 1
    ids = [i.strip() for i in args.only.split(",") if i.strip()]
    review_ids = {i.strip() for i in args.through_review.split(",") if i.strip()}
    now = args.now.astimezone(NPT) if args.now else None
    cache = ReplayCache(args.cache, record=not args.check)
    engine = make_engine(args.database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    client = LLMClient(make_run_recorder(factory), settings, cache=cache,
                       transport=transport if transport is not None else (httpx.MockTransport(_refuse) if args.check else None))
    try:
        if args.seed_company:
            from scripts.seed_demo import DEFAULT_DATA_DIR, seed

            results = seed(DEFAULT_DATA_DIR, args.database_url, client)
            if not all(status is IngestStatus.READY for status in results.values()):
                print("Demo company KB is not fully ingested; see above.")
                return 1
        with factory() as session:
            if load_company(session) is None:
                print("No company profile. Run `python -m api.scripts.seed_demo` first, or pass --seed-company.")
                return 1
            notices = [n for n in load_seed_notices(args.seed_dir) if n.source_url.rsplit("/", 1)[-1][:3] in ids]
            _, tender_ids = upsert_notices(session, notices)

        print(f"{'id':<4} {'status':<9} {'run':<9} {'stages':<44} note")
        failed = False
        for notice, tender_id in zip(notices, tender_ids, strict=True):
            seed_id = notice.source_url.rsplit("/", 1)[-1][:3]
            runs = [run_pipeline(factory, client, tender_id, from_stage=Stage.SCOUT, target=TenderStatus.CHECKED,
                                 settings=settings, now=now)]
            if seed_id in review_ids and runs[0].end_status in (TenderStatus.CHECKED.value, TenderStatus.BLOCKED.value):
                with factory() as session:
                    tender = session.get(Tender, tender_id)
                    if tender.status == TenderStatus.BLOCKED.value:
                        override_block(session, tender, overridden_by=OVERRIDDEN_BY,
                                       reason="Pre-cache: the presenter overrides this block on stage.")
                runs.append(run_pipeline(factory, client, tender_id, target=TenderStatus.REVIEWED, settings=settings,
                                         now=now))
            for run in runs:
                stages = " ".join(f"{s['stage']}:{s['status']}({(s['duration_ms'] or 0) / 1000:.1f}s)" for s in run.stages)
                failed |= run.status == RunStatus.FAILED.value
                print(f"{seed_id:<4} {run.end_status:<9} {run.status:<9} {stages:<44} {run.error or ''}")
        print(f"replay cache {args.cache}: {cache.hits} hits, {cache.misses} misses, "
              f"{len(cache.chat)} chat outputs, {len(cache.embeddings)} embeddings")
        if args.check and cache.misses:
            print("Cache misses: the demo would call the live model. Re-record on the demo KB (see --help).")
            return 1
        return 1 if failed else 0
    finally:
        client.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
