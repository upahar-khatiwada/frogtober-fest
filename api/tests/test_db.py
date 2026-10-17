"""Migrations, constraints and pgvector cosine search (needs Postgres; see conftest.pg_url)."""

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db import Company, Document, KBChunk, make_run_recorder, retrieve, search_chunks
from schemas import AgentRunRecord, DocType, IngestStatus, Stage
from tests.conftest import FakeOllama, alembic_config, bag_of_words_vector


def unit(i: int, dim: int = 1024) -> list[float]:
    v = [0.0] * dim
    v[i] = 1.0
    return v


def blend(a: int, b: int, wb: float) -> list[float]:
    v = [0.0] * 1024
    v[a], v[b] = 1.0 - wb, wb
    return v


def add_company(session) -> Company:
    company = Company(name="Demo", profile_json={"name": "Demo"})
    session.add(company)
    session.commit()
    return company


def add_doc(session, company, doc_type=DocType.OTHER, status=IngestStatus.READY, chunks=()) -> Document:
    doc = Document(
        company_id=company.id, filename=f"{doc_type}.txt", doc_type=doc_type.value, content=b"x", sha256="0" * 64,
        ingest_status=status.value,
    )
    doc.chunks = [
        KBChunk(chunk_index=i, content=content, token_count=1, embedding=vector) for i, (content, vector) in enumerate(chunks)
    ]
    session.add(doc)
    session.commit()
    return doc


def test_migration_matches_models(pg_url, migrated_engine):
    command.check(alembic_config(pg_url))  # raises if autogenerate would emit any operation


def test_embedding_column_is_vector_1024(db_session):
    column_type = db_session.execute(
        text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'kb_chunks'::regclass AND attname = 'embedding'")
    ).scalar_one()
    assert column_type == "vector(1024)"


def test_nepal_columns_exist(db_session):
    def columns(table: str) -> set[str]:
        rows = db_session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table})
        return {r[0] for r in rows}

    assert {"procurement_type", "method", "province", "district", "deadline_bs", "estimated_cost_npr", "language"} <= columns("tenders")
    assert {"doc_type", "expires_on", "fiscal_year_bs", "ingest_status"} <= columns("documents")
    assert {"pan_number", "vat_number", "licence_classes", "province"} <= columns("company")
    assert {"attempts", "error", "raw_output"} <= columns("agent_runs")


def test_check_constraints_reject_unknown_enum_values(db_session):
    company = add_company(db_session)
    db_session.add(Document(company_id=company.id, filename="a", doc_type="passport", content=b"", sha256="0" * 64))
    with pytest.raises(IntegrityError, match="ck_documents_doc_type"):
        db_session.commit()
    db_session.rollback()
    db_session.execute(text("INSERT INTO tenders (status) VALUES ('new')"))
    with pytest.raises(IntegrityError, match="ck_tenders_status"):
        db_session.execute(text("INSERT INTO tenders (status) VALUES ('submitted')"))


def test_downgrade_and_upgrade_round_trip(pg_url, migrated_engine):
    cfg = alembic_config(pg_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_search_orders_by_cosine_similarity(db_session):
    company = add_company(db_session)
    add_doc(db_session, company, chunks=[("far", unit(5)), ("near", blend(0, 5, 0.2)), ("exact", unit(0))])

    hits = search_chunks(db_session, unit(0), k=2)

    assert [h.content for h in hits] == ["exact", "near"]
    assert hits[0].similarity == pytest.approx(1.0)
    assert 0 < hits[1].similarity < 1
    assert hits[0].chunk_id > 0 and hits[0].filename == "other.txt"


def test_search_filters(db_session):
    company = add_company(db_session)
    add_doc(db_session, company, DocType.TAX_CLEARANCE, chunks=[("tax", unit(0))])
    add_doc(db_session, company, DocType.EXPERIENCE_CERTIFICATE, chunks=[("exp", blend(0, 1, 0.5))])
    add_doc(db_session, company, DocType.COMPANY_PROFILE, IngestStatus.PROCESSING, chunks=[("half-ingested", unit(0))])

    assert [h.content for h in search_chunks(db_session, unit(0), k=10)] == ["tax", "exp"]
    hits = search_chunks(db_session, unit(0), k=10, doc_types=[DocType.EXPERIENCE_CERTIFICATE])
    assert [h.content for h in hits] == ["exp"]
    assert search_chunks(db_session, unit(0), k=10, company_id=company.id + 1) == []


def test_search_rejects_wrong_dimension(db_session):
    with pytest.raises(ValueError, match="1024"):
        search_chunks(db_session, [1.0] * 768)


def test_retrieve_embeds_query_with_llm_client(db_session, make_client):
    company = add_company(db_session)
    texts = [
        "Completed 2.3 km gravel road and side drains for the rural municipality",
        "Tax clearance certificate issued by the Inland Revenue Office",
        "Company owns two excavators, a roller and three tippers",
    ]
    add_doc(db_session, company, chunks=[(t, bag_of_words_vector(t)) for t in texts])
    client = make_client(FakeOllama(embed_fn=bag_of_words_vector), [])

    [top] = retrieve(db_session, client, "gravel road experience", k=1)

    assert top.content == texts[0]


def test_run_recorder_writes_agent_runs_row(session_factory, db_session):
    record = make_run_recorder(session_factory)
    record(AgentRunRecord(stage=Stage.SCOUT, model="m", input_hash="h", output_json={"a": 1}, latency_ms=5, ok=True, attempts=1))
    row = db_session.execute(text("SELECT stage, ok, attempts, output_json FROM agent_runs")).one()
    assert tuple(row) == ("scout", True, 1, {"a": 1})
