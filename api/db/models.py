"""SQLAlchemy 2 models for spec section 11, extended for Nepal.

The Alembic migrations in `alembic/versions/` are the source of truth for
the live schema; `tests/test_db.py` checks the two never drift apart.

Enum-valued columns are TEXT with a CHECK constraint built from the
`schemas.enums` values, so the DB rejects anything the contracts would.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from pipeline.llm import EMBED_DIM
from schemas.enums import (
    ComplianceStatus,
    DocType,
    IngestStatus,
    ItemSource,
    MatchDecision,
    NoticeLanguage,
    ProcurementMethod,
    ProcurementType,
    ProposalLanguage,
    ProposalStatus,
    Province,
    RunStatus,
    Severity,
    Stage,
    TenderStatus,
)


class Base(DeclarativeBase):
    pass


def enum_check(column: str, enum: type[StrEnum], name: str) -> CheckConstraint:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return CheckConstraint(f"{column} IN ({values})", name=name)


TS = DateTime(timezone=True)


class Company(Base):
    __tablename__ = "company"
    __table_args__ = (enum_check("province", Province, "ck_company_province"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    sectors: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    services: Mapped[str] = mapped_column(Text, server_default="")
    location: Mapped[str | None] = mapped_column(Text)
    # Latest fiscal year's turnover, denormalised from profile_json for list views.
    turnover_npr: Mapped[int | None] = mapped_column(BigInteger)
    certifications: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB)  # CompanyProfile
    # Nepal extensions
    province: Mapped[str | None] = mapped_column(Text)
    pan_number: Mapped[str | None] = mapped_column(Text)
    vat_number: Mapped[str | None] = mapped_column(Text)
    licence_classes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        enum_check("doc_type", DocType, "ck_documents_doc_type"),
        enum_check("ingest_status", IngestStatus, "ck_documents_ingest_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(Text)
    expires_on: Mapped[date | None] = mapped_column(Date)
    raw_text: Mapped[str | None] = mapped_column(Text)
    # Ingestion bookkeeping
    content_type: Mapped[str | None] = mapped_column(Text)
    content: Mapped[bytes] = mapped_column(LargeBinary)  # original upload, kept for the submission package
    sha256: Mapped[str] = mapped_column(String(64))
    fiscal_year_bs: Mapped[str | None] = mapped_column(Text)
    value_npr: Mapped[int | None] = mapped_column(BigInteger)
    ingest_status: Mapped[str] = mapped_column(Text, server_default=IngestStatus.PENDING.value)
    ingest_error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="documents")
    chunks: Mapped[list["KBChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KBChunk.chunk_index"
    )


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index(
            "ix_kb_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    # bge-m3 = 1024 dims. Fixed (spec section 11); changing it needs a migration and a re-embed.
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))

    document: Mapped[Document] = relationship(back_populates="chunks")


class Tender(Base):
    __tablename__ = "tenders"
    __table_args__ = (
        enum_check("status", TenderStatus, "ck_tenders_status"),
        enum_check("procurement_type", ProcurementType, "ck_tenders_procurement_type"),
        enum_check("method", ProcurementMethod, "ck_tenders_method"),
        enum_check("province", Province, "ck_tenders_province"),
        enum_check("language", NoticeLanguage, "ck_tenders_language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_url: Mapped[str | None] = mapped_column(Text, unique=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    buyer: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime | None] = mapped_column(TS, index=True)  # AD, timezone-aware (NPT in practice)
    location: Mapped[str | None] = mapped_column(Text)
    record_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # TenderRecord
    status: Mapped[str] = mapped_column(Text, server_default=TenderStatus.NEW.value, index=True)
    # Nepal extensions (denormalised from record_json for filtering)
    procurement_type: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    deadline_bs: Mapped[str | None] = mapped_column(Text)  # BS YYYY-MM-DD, never parsed as AD
    estimated_cost_npr: Mapped[int | None] = mapped_column(BigInteger)  # spec section 11 `budget`
    language: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (enum_check("decision", MatchDecision, "ck_matches_decision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ComplianceItemRow(Base):
    __tablename__ = "compliance_items"
    __table_args__ = (
        enum_check("status", ComplianceStatus, "ck_compliance_items_status"),
        enum_check("severity", Severity, "ck_compliance_items_severity"),
        enum_check("source", ItemSource, "ck_compliance_items_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    requirement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    # Additive: deterministic rule id (nepal/rules.yaml) and the item's explanation.
    rule_id: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    # Additive (0002): which layer made the item, its structured evidence, and what the bidder must do.
    source: Mapped[str] = mapped_column(Text, server_default=ItemSource.RULE.value)
    evidence_chunk_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default="{}")
    evidence_document_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default="{}")
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    action_needed: Mapped[str | None] = mapped_column(Text)
    requirement_index: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ComplianceOverrideRow(Base):
    """A person's explicit decision to proceed despite hard compliance failures (who, when, why, which failures)."""

    __tablename__ = "compliance_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    overridden_by: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    # ComplianceItem.key of each hard failure accepted; a later report with a new hard failure is not covered.
    hard_failures: Mapped[list[Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ProposalRow(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        enum_check("status", ProposalStatus, "ck_proposals_status"),
        enum_check("language", ProposalLanguage, "ck_proposals_language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    sections: Mapped[list[Any]] = mapped_column(JSONB)  # ProposalSection dumps, incl. cited_chunk_ids
    language: Mapped[str | None] = mapped_column(Text)
    review_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # ReviewReport
    status: Mapped[str] = mapped_column(Text, server_default=ProposalStatus.DRAFT.value)
    approved_at: Mapped[datetime | None] = mapped_column(TS)
    # Additive (0005): the human gate. Approval needs a review, a verdict other than fail, and an open after the review.
    approved_by: Mapped[str | None] = mapped_column(Text)
    approval_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    opened_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (enum_check("stage", Stage, "ck_agent_runs_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # No FK: a Scout run happens before its tender row exists (spec section 11 has none either).
    tender_id: Mapped[int | None] = mapped_column(Integer, index=True)
    stage: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    error: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[str | None] = mapped_column(Text)
    # Set while the orchestrator runs this tender (db.runs.current_pipeline_run); null for CLI/ad-hoc calls.
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="SET NULL"), index=True)
    # Replayed from the LLM replay cache (pre-cached demo), not a live model call.
    cached: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


_ACTIVE_RUN = f"status IN ('{RunStatus.QUEUED.value}', '{RunStatus.RUNNING.value}')"


class PipelineRun(Base):
    """One orchestrated pass over one tender (pipeline/orchestrator.py), polled via GET /runs/{id}."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        enum_check("status", RunStatus, "ck_pipeline_runs_status"),
        enum_check("target", TenderStatus, "ck_pipeline_runs_target"),
        # At most one queued/running run per tender: a second analyze gets 409, not a race.
        Index("uq_pipeline_runs_active_tender", "tender_id", unique=True, postgresql_where=text(_ACTIVE_RUN)),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    target: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=RunStatus.QUEUED.value)
    start_status: Mapped[str] = mapped_column(Text)
    resumed_from: Mapped[str | None] = mapped_column(Text)
    end_status: Mapped[str | None] = mapped_column(Text)
    stages: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")  # list[StageRun]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(TS)
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    # Bumped on every stage start/finish and every agent_runs row; a stale heartbeat means the worker died.
    heartbeat_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
