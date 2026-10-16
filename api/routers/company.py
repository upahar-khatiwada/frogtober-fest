"""Company profile and knowledge-base endpoints (spec section 10.2).

Not implemented yet: see routers/tenders.py docstring.
"""

from fastapi import APIRouter, HTTPException, status

from schemas import CompanyProfile

router = APIRouter(prefix="/company", tags=["company"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."
_501 = {status.HTTP_501_NOT_IMPLEMENTED: {"description": "Not implemented yet"}}


@router.post("", responses=_501)
def upsert_company(profile: CompanyProfile) -> CompanyProfile:
    """Create or update company profile."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/documents", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def upload_company_document():
    """Upload document; parse, chunk, embed (ingest/parse_docs.py, ingest/embed.py)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
