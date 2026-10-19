"""Reference data for the tender detail page: Nepal rules and the KB chunk text behind compliance evidence."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Document, KBChunk
from deps import get_now, get_session
from nepal.dates import NPT
from nepal.rules import Rule, load_rules
from schemas._base import Contract
from schemas.enums import DocType

router = APIRouter(tags=["reference"])


class KBChunkView(Contract):
    """One knowledge-base chunk with its document, so the UI can show evidence next to a compliance item."""

    chunk_id: int
    document_id: int
    filename: str
    doc_type: DocType
    chunk_index: int
    content: str
    expires_on: date | None = None
    is_expired: bool | None = None
    fiscal_year_bs: str | None = None


@router.get("/rules")
def list_rules() -> list[Rule]:
    """The deterministic Nepal rules (nepal/rules.yaml): description, severity, source URL, verified flag."""
    return list(load_rules())


@router.get("/chunks")
def get_chunks(
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(get_now)],
    ids: Annotated[list[int], Query(max_length=100, description="kb_chunks.id values; unknown ids are omitted")],
) -> list[KBChunkView]:
    today = now.astimezone(NPT).date()
    rows = session.execute(
        select(KBChunk, Document).join(Document, KBChunk.document_id == Document.id).where(KBChunk.id.in_(ids)).order_by(KBChunk.id)
    )
    return [
        KBChunkView(
            chunk_id=chunk.id,
            document_id=doc.id,
            filename=doc.filename,
            doc_type=DocType(doc.doc_type),
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            expires_on=doc.expires_on,
            is_expired=None if doc.expires_on is None else doc.expires_on < today,
            fiscal_year_bs=doc.fiscal_year_bs,
        )
        for chunk, doc in rows
    ]