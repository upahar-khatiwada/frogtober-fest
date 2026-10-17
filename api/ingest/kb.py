"""Knowledge-base ingestion: store an upload, then parse -> chunk -> embed -> kb_chunks.

Used by POST /company/documents (as a background task) and by the demo
seed script. The document row's `ingest_status` records the outcome, so
nothing fails silently: scans end as `needs_ocr`, errors as `failed`.
"""

import hashlib
import logging
from datetime import date

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from db.models import Document, KBChunk
from ingest.chunking import chunk_text
from ingest.embed import embed_chunks
from ingest.parse_docs import ParseError, parse_document
from pipeline.llm import LLMClient, LLMError
from schemas.enums import DocType, IngestStatus

log = logging.getLogger(__name__)


def create_document(
    session: Session,
    *,
    company_id: int,
    filename: str,
    content: bytes,
    doc_type: DocType,
    content_type: str | None = None,
    expires_on: date | None = None,
    fiscal_year_bs: str | None = None,
    value_npr: int | None = None,
) -> Document:
    document = Document(
        company_id=company_id,
        filename=filename,
        content=content,
        content_type=content_type,
        sha256=hashlib.sha256(content).hexdigest(),
        doc_type=doc_type.value,
        expires_on=expires_on,
        fiscal_year_bs=fiscal_year_bs,
        value_npr=value_npr,
        ingest_status=IngestStatus.PENDING.value,
    )
    session.add(document)
    session.commit()
    return document


def _finish(session: Session, document: Document, status: IngestStatus, error: str | None = None) -> None:
    document.ingest_status = status.value
    document.ingest_error = error
    session.commit()


def ingest_document(session: Session, document: Document, client: LLMClient) -> IngestStatus:
    """Parse, chunk and embed one stored document. Safe to re-run (old chunks are replaced)."""
    document.ingest_status = IngestStatus.PROCESSING.value
    document.ingest_error = None
    session.execute(delete(KBChunk).where(KBChunk.document_id == document.id))
    session.commit()

    try:
        parsed = parse_document(document.content, document.filename)
    except ParseError as exc:
        _finish(session, document, IngestStatus.FAILED, str(exc))
        return IngestStatus.FAILED

    document.raw_text = parsed.text
    document.page_count = parsed.page_count
    document.warnings = parsed.warnings
    if parsed.needs_ocr:
        _finish(session, document, IngestStatus.NEEDS_OCR, "scanned PDF: no extractable text, and OCR is out of scope")
        return IngestStatus.NEEDS_OCR

    chunks = chunk_text(parsed.text)
    if not chunks:
        _finish(session, document, IngestStatus.FAILED, "document has no text to index")
        return IngestStatus.FAILED

    try:
        vectors = embed_chunks(client, [c.text for c in chunks])
    except LLMError as exc:
        _finish(session, document, IngestStatus.FAILED, f"embedding failed: {exc}")
        return IngestStatus.FAILED

    session.add_all(
        KBChunk(document_id=document.id, chunk_index=c.index, content=c.text, token_count=c.token_count, embedding=v)
        for c, v in zip(chunks, vectors, strict=True)
    )
    _finish(session, document, IngestStatus.READY)
    return IngestStatus.READY


def ingest_document_by_id(session_factory: sessionmaker[Session], client: LLMClient, document_id: int) -> None:
    """Background-task entry point: own session, never raises (status carries the error)."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is None:
            return
        try:
            ingest_document(session, document, client)
        except Exception as exc:  # last resort: record it instead of losing it in a background thread
            log.exception("ingest of document %s crashed", document_id)
            session.rollback()
            _finish(session, document, IngestStatus.FAILED, f"internal error: {exc}")
