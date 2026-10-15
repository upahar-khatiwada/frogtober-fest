"""Tender endpoints (spec section 10.2).

Not implemented yet: schemas, DB models and the Scout/Matching/Compliance
agents land in a later prompt. These stubs exist so the route shape and
OpenAPI schema (consumed by web/'s `gen:api` script) are stable early.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/tenders", tags=["tenders"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."


@router.post("/scrape", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def scrape_tenders():
    """Run the scraper or load seed data; enqueue Scout."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def list_tenders():
    """Ranked list with filters."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{tender_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_tender(tender_id: int):
    """Tender detail, match result, compliance report."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/{tender_id}/analyze", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def analyze_tender(tender_id: int):
    """Run Matching and Compliance."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/{tender_id}/proposal", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def generate_proposal(tender_id: int):
    """Run Proposal and Review."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)