"""Database layer: SQLAlchemy 2 models (spec section 11 + Nepal extensions), sessions, KB search."""

from db.models import (
    AgentRunRow,
    Base,
    Company,
    ComplianceItemRow,
    Document,
    KBChunk,
    Match,
    ProposalRow,
    Tender,
)
from db.runs import make_run_recorder
from db.search import ChunkHit, retrieve, search_chunks
from db.session import get_session, get_sessionmaker, make_engine, sqlalchemy_url

__all__ = [
    "AgentRunRow",
    "Base",
    "ChunkHit",
    "Company",
    "ComplianceItemRow",
    "Document",
    "KBChunk",
    "Match",
    "ProposalRow",
    "Tender",
    "get_session",
    "get_sessionmaker",
    "make_engine",
    "make_run_recorder",
    "retrieve",
    "search_chunks",
    "sqlalchemy_url",
]
