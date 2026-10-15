"""Centralized settings for the Tenderly API, read from the environment.

Per CLAUDE.md hard rule 1, the LLM endpoint/model and embedding model are
configured here via env vars rather than hard-coded, so the whole stack can
point at a different Ollama host (or an open-weight-only hosted fallback)
without a code change.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Ollama (hard rule 1: open-weight models only, one client in pipeline/llm.py) ---
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b-instruct"
    embed_model: str = "bge-m3"

    # --- Database ---
    database_url: str = "postgresql://tenderly:tenderly@localhost:5432/tenderly"

    # --- CORS: the Next.js web origin(s) allowed to call this API ---
    web_origin: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Import this, not Settings(), elsewhere."""
    return Settings()