"""Tenderly API entrypoint.

Run with: uv run fastapi dev main.py  (see CLAUDE.md Commands table)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import company, proposals, runs, tenders

settings = get_settings()

app = FastAPI(
    title="Tenderly API",
    description="Agentic tender-to-proposal pipeline for Nepali SMEs.",
    version="0.1.0",
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


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check used by docker-compose and the deploy verification step."""
    return {"status": "ok"}