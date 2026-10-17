"""Shared FastAPI dependencies. Tests override these via `app.dependency_overrides`."""

from functools import lru_cache

from db.runs import make_run_recorder
from db.session import get_session, get_sessionmaker
from pipeline.llm import LLMClient


@lru_cache
def get_llm_client() -> LLMClient:
    """The one Ollama client (hard rule 3); its agent_runs rows go to the DB (hard rule 9)."""
    return LLMClient(make_run_recorder(get_sessionmaker()))


__all__ = ["get_llm_client", "get_session", "get_sessionmaker"]
