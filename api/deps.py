"""Shared FastAPI dependencies. Tests override these via `app.dependency_overrides`."""

from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from config import get_settings
from db.runs import make_run_recorder
from db.session import get_session, get_sessionmaker
from ingest.scraper import KANKAI_BASE_URL, PoliteFetcher
from nepal.dates import NPT
from pipeline.llm import LLMClient


@lru_cache
def get_llm_client() -> LLMClient:
    """The one Ollama client (hard rule 3); its agent_runs rows go to the DB (hard rule 9)."""
    return LLMClient(make_run_recorder(get_sessionmaker()))


def get_now() -> datetime:
    """Current time in Nepal (deadline checks, days left). Tests pin it."""
    return datetime.now(NPT)


def get_seed_dir() -> Path:
    return get_settings().seed_tenders_dir


def get_kankai_fetcher() -> Iterator[PoliteFetcher]:
    """Live scraper client (the only one: one source). Tests swap in a MockTransport-backed fetcher."""
    settings = get_settings()
    fetcher = PoliteFetcher(
        KANKAI_BASE_URL,
        user_agent=settings.scraper_ua,
        cache_dir=settings.scraper_cache_dir / "kankai",
        min_delay_s=settings.scraper_min_delay_s,
    )
    try:
        yield fetcher
    finally:
        fetcher.close()


__all__ = ["get_kankai_fetcher", "get_llm_client", "get_now", "get_seed_dir", "get_session", "get_sessionmaker", "get_settings"]
