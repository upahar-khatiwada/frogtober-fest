"""Database layer: SQLAlchemy 2 models (spec section 11 + Nepal extensions), sessions, KB search."""

from db.models import (
    AgentRunRow,
    Base,
    Company,
    ComplianceItemRow,
    Document,
    KBChunk,
    Match,
    PipelineRun,
    ProposalRow,
    Tender,
)
from db.runs import current_pipeline_run, make_run_recorder, pipeline_run_context
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
    "PipelineRun",
    "ProposalRow",
    "Tender",
    "get_session",
    "get_sessionmaker",
    "make_engine",
    "make_run_recorder",
    "current_pipeline_run",
    "pipeline_run_context",
    "retrieve",
    "search_chunks",
    "sqlalchemy_url",
]
