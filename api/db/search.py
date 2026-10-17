"""Top-k KB retrieval by cosine similarity (spec section 10.4).

Matching and Proposal call `search_chunks` with a query vector from
`LLMClient.embed` (or `retrieve`, which embeds the query for you). Only
chunks of fully ingested documents are searched.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Document, KBChunk
from pipeline.llm import EMBED_DIM, LLMClient
from schemas.enums import DocType, IngestStatus


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int  # cite this id in proposal sections / compliance evidence (hard rule 8)
    document_id: int
    filename: str
    doc_type: DocType
    expires_on: date | None
    chunk_index: int
    content: str
    similarity: float  # cosine similarity, 1.0 = identical direction


def search_chunks(
    session: Session,
    query_vector: Sequence[float],
    k: int = 5,
    *,
    company_id: int | None = None,
    doc_types: Sequence[DocType] | None = None,
) -> list[ChunkHit]:
    if len(query_vector) != EMBED_DIM:
        raise ValueError(f"query vector has {len(query_vector)} dims; kb_chunks expects {EMBED_DIM}")
    if k < 1:
        raise ValueError("k must be >= 1")

    distance = KBChunk.embedding.cosine_distance(list(query_vector))
    stmt = (
        select(KBChunk, Document, distance.label("distance"))
        .join(Document, KBChunk.document_id == Document.id)
        .where(Document.ingest_status == IngestStatus.READY.value)
        .order_by(distance, KBChunk.id)
        .limit(k)
    )
    if company_id is not None:
        stmt = stmt.where(Document.company_id == company_id)
    if doc_types:
        stmt = stmt.where(Document.doc_type.in_([t.value for t in doc_types]))

    return [
        ChunkHit(
            chunk_id=chunk.id,
            document_id=doc.id,
            filename=doc.filename,
            doc_type=DocType(doc.doc_type),
            expires_on=doc.expires_on,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            similarity=1.0 - float(dist),
        )
        for chunk, doc, dist in session.execute(stmt)
    ]


def retrieve(session: Session, client: LLMClient, query: str, k: int = 5, **filters) -> list[ChunkHit]:
    """Embed `query` with the one LLM client (hard rule 3), then `search_chunks`."""
    [vector] = client.embed([query])
    return search_chunks(session, vector, k, **filters)
