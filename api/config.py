"""Centralized settings for the Tenderly API, read from the environment.

Per CLAUDE.md hard rule 1, the LLM endpoint/model and embedding model are
configured here via env vars rather than hard-coded, so the whole stack can
point at a different Ollama host (or an open-weight-only hosted fallback)
without a code change.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Ollama (hard rule 1: open-weight models only, one client in pipeline/llm.py) ---
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b-instruct"
    embed_model: str = "bge-m3"
    # Per-call HTTP timeout (spec section 10.5). Generous: a 7B model on CPU is slow.
    llm_timeout_s: float = 180.0
    # Ollama context window per chat call. Ollama's default (2048-4096) silently drops the
    # start of the prompt (the system prompt) on long Devanagari notices; 0 = Ollama default.
    llm_num_ctx: int = 8192

    # --- Database ---
    database_url: str = "postgresql://tenderly:tenderly@localhost:5432/tenderly"

    # --- Tender ingestion (POST /tenders/scrape) ---
    # Synthetic seed notices: the primary demo source (spec section 17).
    seed_tenders_dir: Path = _API_DIR.parent / "data" / "seed_tenders"
    # Live scraper (a bonus, never a dependency). An honest UA; set SCRAPER_CONTACT
    # to a URL or email so a site admin can reach whoever runs it.
    scraper_user_agent: str = "TenderlyBot/0.1 (Frogtoberfest research prototype; read-only; honours robots.txt)"
    scraper_contact: str = ""
    # Floor on the gap between requests; robots.txt Crawl-delay wins if larger.
    scraper_min_delay_s: float = 10.0
    scraper_cache_dir: Path = _API_DIR / ".cache" / "scraper"

    # --- Matching (agents/matching.py). Company policy knobs, not procurement law. ---
    # score >= threshold -> pursue (status matched); below -> skip (Compliance does not run).
    match_threshold: int = 60
    # Final score = llm_weight * semantic (LLM) + (1 - llm_weight) * deterministic fit points.
    match_llm_weight: float = 0.6
    # Hard skip when the estimated cost exceeds this multiple of the company's average annual turnover.
    match_max_cost_to_turnover: float = 2.0
    # Average turnover over this many most recent fiscal years in the profile.
    match_turnover_years: int = 3
    # Fewer days left than this loses deadline points (not a skip).
    match_tight_deadline_days: int = 7
    # KB chunks retrieved (cosine top-k) and shown to the model.
    match_top_k: int = 5
    # Ask the LLM even when a deterministic rule already forces skip (costs a model call per skipped tender).
    match_llm_on_hard_skip: bool = False

    # --- CORS: the Next.js web origin(s) allowed to call this API ---
    web_origin: str = "http://localhost:3000"

    @property
    def scraper_ua(self) -> str:
        return f"{self.scraper_user_agent[:-1]}; +{self.scraper_contact})" if self.scraper_contact else self.scraper_user_agent

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Import this, not Settings(), elsewhere."""
    return Settings()