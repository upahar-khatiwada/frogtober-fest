"""Engine and session factory. FastAPI routes get a session via `get_session`."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings


def sqlalchemy_url(url: str) -> str:
    """`postgresql://...` (what docker-compose and .env use) -> the psycopg 3 driver URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def make_engine(url: str) -> Engine:
    return create_engine(sqlalchemy_url(url), pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Process-wide session factory. Tests override this dependency."""
    return sessionmaker(make_engine(get_settings().database_url), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session
