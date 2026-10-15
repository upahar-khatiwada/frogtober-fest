"""Company profile and knowledge-base endpoints (spec section 10.2).

Not implemented yet: see routers/tenders.py docstring.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/company", tags=["company"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def upsert_company():
    """Create or update company profile."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/documents", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def upload_company_document():
    """Upload document; parse, chunk, embed (ingest/parse_docs.py, ingest/embed.py)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)