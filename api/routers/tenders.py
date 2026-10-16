"""Tender endpoints (spec section 10.2).

Not implemented yet: DB models and the Scout/Matching/Compliance agents
land in a later prompt. The stubs declare their response models so the
OpenAPI schema (consumed by web/'s `gen:api` script) carries the stage
contracts from schemas/ already.
"""

from fastapi import APIRouter, HTTPException, status

from schemas import Proposal, TenderDetail

router = APIRouter(prefix="/tenders", tags=["tenders"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."
_501 = {status.HTTP_501_NOT_IMPLEMENTED: {"description": "Not implemented yet"}}


@router.post("/scrape", responses=_501)
def scrape_tenders() -> list[TenderDetail]:
    """Run the scraper or load seed data; enqueue Scout."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("", responses=_501)
def list_tenders() -> list[TenderDetail]:
    """Ranked list with filters."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{tender_id}", responses=_501)
def get_tender(tender_id: int) -> TenderDetail:
    """Tender detail, match result, compliance report."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/{tender_id}/analyze", responses=_501)
def analyze_tender(tender_id: int) -> TenderDetail:
    """Run Matching and Compliance."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/{tender_id}/proposal", responses=_501)
def generate_proposal(tender_id: int) -> Proposal:
    """Run Proposal and Review."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
