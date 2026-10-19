"""Tenderly API entrypoint.

Run with: uv run fastapi dev main.py  (see CLAUDE.md Commands table)
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from deps import get_sessionmaker
from pipeline.orchestrator import reap_stale_runs
from routers import company, proposals, reference, runs, tenders

settings = get_settings()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: pipeline runs left queued/running by a previous process can never finish; mark them failed."""
    factory = app.dependency_overrides.get(get_sessionmaker, get_sessionmaker)()
    try:
        if reaped := reap_stale_runs(factory):
            log.warning("marked %d interrupted pipeline run(s) failed", reaped)
    except Exception as exc:  # DB not up yet: the API still starts; GET /runs reaps stale runs later
        log.warning("could not reap interrupted pipeline runs at startup: %s", exc)
    yield


app = FastAPI(
    title="Tenderly API",
    description="Agentic tender-to-proposal pipeline for Nepali SMEs.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenders.router)
app.include_router(company.router)
app.include_router(proposals.router)
app.include_router(runs.router)
app.include_router(reference.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check used by docker-compose and the deploy verification step."""
    return {"status": "ok"}