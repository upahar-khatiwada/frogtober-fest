"""Company profile and knowledge-base endpoints (spec section 10.2).

Single-company MVP (multi-tenant accounts are out of scope): POST /company
creates the one company row or updates it.
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from db.models import Company, Document, KBChunk
from deps import get_llm_client, get_session, get_sessionmaker
from ingest.kb import create_document, ingest_document_by_id
from ingest.parse_docs import ParseError, detect_kind
from nepal.dates import NPT, bs_to_ad, parse_bs_date
from pipeline.llm import LLMClient
from schemas import CompanyDocumentView, CompanyProfile, CompanyView, DocType, IngestStatus
from schemas._base import FiscalYearBS

router = APIRouter(prefix="/company", tags=["company"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_FISCAL_YEAR = TypeAdapter(FiscalYearBS)

SessionDep = Annotated[Session, Depends(get_session)]


def _company(session: Session) -> Company | None:
    return session.scalars(select(Company).order_by(Company.id).limit(1)).first()


def _company_view(company: Company) -> CompanyView:
    return CompanyView(**company.profile_json, id=company.id, updated_at=company.updated_at)


def _document_view(document: Document, chunk_count: int, today: date) -> CompanyDocumentView:
    return CompanyDocumentView(
        id=document.id,
        filename=document.filename,
        doc_type=DocType(document.doc_type),
        expires_on=document.expires_on,
        is_expired=None if document.expires_on is None else document.expires_on < today,
        fiscal_year_bs=document.fiscal_year_bs,
        value_npr=document.value_npr,
        ingest_status=IngestStatus(document.ingest_status),
        ingest_error=document.ingest_error,
        warnings=list(document.warnings or []),
        page_count=document.page_count,
        chunk_count=chunk_count,
        uploaded_at=document.uploaded_at,
    )


def upsert_company_profile(session: Session, profile: CompanyProfile) -> Company:
    """Shared by POST /company and the seed script."""
    company = _company(session) or Company()
    latest = max(profile.turnover, key=lambda t: t.fiscal_year_bs, default=None)
    company.name = profile.name
    company.sectors = profile.sectors
    company.services = profile.services
    company.location = profile.location
    company.turnover_npr = latest.amount_npr if latest else None
    company.certifications = profile.certifications
    company.profile_json = profile.model_dump(mode="json")
    company.province = profile.province.value if profile.province else None
    company.pan_number = profile.pan_number
    company.vat_number = profile.vat_number
    company.licence_classes = sorted({lic.licence_class.value for lic in profile.licences if lic.licence_class})
    company.updated_at = func.now()
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.post("")
def upsert_company(profile: CompanyProfile, session: SessionDep) -> CompanyView:
    """Create or update company profile."""
    return _company_view(upsert_company_profile(session, profile))


@router.get("", responses={404: {"description": "No company profile yet"}})
def get_company(session: SessionDep) -> CompanyView:
    company = _company(session)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No company profile yet; POST /company first.")
    return _company_view(company)


def _resolve_expiry(expires_on: date | None, expires_on_bs: str | None) -> date | None:
    """Accept the expiry in AD or BS; BS is converted deterministically (hard rule 5)."""
    if not expires_on_bs:
        return expires_on
    try:
        converted = bs_to_ad(parse_bs_date(expires_on_bs))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"expires_on_bs: {exc}") from exc
    if expires_on is not None and expires_on != converted:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"expires_on ({expires_on}) and expires_on_bs ({expires_on_bs} = {converted} AD) disagree",
        )
    return converted


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"description": "No company profile yet"}, 413: {}, 415: {}},
)
def upload_company_document(
    background: BackgroundTasks,
    session: SessionDep,
    session_factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
    client: Annotated[LLMClient, Depends(get_llm_client)],
    file: Annotated[UploadFile, File(description="PDF, DOCX or UTF-8 TXT")],
    doc_type: Annotated[DocType, Form()],
    expires_on: Annotated[date | None, Form(description="Expiry date (AD)")] = None,
    expires_on_bs: Annotated[str | None, Form(description="Expiry date (BS, e.g. 2084-03-31); converted to AD")] = None,
    fiscal_year_bs: Annotated[str | None, Form(description='BS fiscal year the document covers, e.g. "2082/83"')] = None,
    value_npr: Annotated[int | None, Form(ge=0, description="Contract value or guarantee amount, NPR")] = None,
) -> CompanyDocumentView:
    """Upload document; parse, chunk and embed it in the background. Poll GET /company/documents."""
    company = _company(session)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No company profile yet; POST /company first.")
    filename = file.filename or "upload"
    try:
        detect_kind(filename)
    except ParseError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    if fiscal_year_bs:
        try:
            _FISCAL_YEAR.validate_python(fiscal_year_bs)
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"fiscal_year_bs: {exc.errors()[0]['msg']}") from exc
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file is larger than 20 MB")
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file is empty")

    document = create_document(
        session,
        company_id=company.id,
        filename=filename,
        content=content,
        content_type=file.content_type,
        doc_type=doc_type,
        expires_on=_resolve_expiry(expires_on, expires_on_bs),
        fiscal_year_bs=fiscal_year_bs or None,
        value_npr=value_npr,
    )
    background.add_task(ingest_document_by_id, session_factory, client, document.id)
    return _document_view(document, 0, datetime.now(NPT).date())


@router.get("/documents")
def list_company_documents(session: SessionDep) -> list[CompanyDocumentView]:
    """Uploaded documents with ingestion status and computed expiry."""
    counts = (
        select(KBChunk.document_id, func.count().label("n")).group_by(KBChunk.document_id).subquery()
    )
    rows = session.execute(
        select(Document, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.document_id == Document.id)
        .order_by(Document.id)
    )
    today = datetime.now(NPT).date()
    return [_document_view(doc, n, today) for doc, n in rows]
