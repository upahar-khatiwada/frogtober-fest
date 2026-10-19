"""Tender endpoints (spec section 10.2).

POST /tenders/scrape is implemented. The rest are stubs until the
Scout/Matching/Compliance agents land; they declare their response models
so the OpenAPI schema (consumed by web/'s `gen:api` script) carries the
stage contracts from schemas/ already.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from deps import get_kankai_fetcher, get_seed_dir, get_session
from ingest.notices import upsert_notices
from ingest.scraper import PoliteFetcher, scrape_kankai
from ingest.seed_tenders import SeedDataError, load_seed_notices
from schemas import Proposal, ScrapeReport, ScrapeRequest, SkippedNotice, TenderDetail, TenderSource

router = APIRouter(prefix="/tenders", tags=["tenders"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."
_501 = {status.HTTP_501_NOT_IMPLEMENTED: {"description": "Not implemented yet"}}


@router.post("/scrape", responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Seed data missing or unreadable"}})
def scrape_tenders(
    session: Annotated[Session, Depends(get_session)],
    seed_dir: Annotated[Path, Depends(get_seed_dir)],
    fetcher: Annotated[PoliteFetcher, Depends(get_kankai_fetcher)],
    request: Annotated[ScrapeRequest | None, Body()] = None,
) -> ScrapeReport:
    """Load the synthetic seed set (default) or run the live scraper; upsert raw notices by source_url.

    New tenders get status `new` and raw text only. Scout is not enqueued yet (it lands with
    the Scout agent). The live source is slow on purpose (>= 10 s between requests).
    """
    request = request or ScrapeRequest()
    skipped: list[SkippedNotice] = []
    blocked = None
    if request.source is TenderSource.SEED:
        try:
            notices = load_seed_notices(seed_dir)
        except SeedDataError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    else:
        outcome = scrape_kankai(fetcher, max_pages=request.max_pages, max_notices=request.max_notices)
        notices, blocked = outcome.notices, outcome.blocked
        skipped = [SkippedNotice(url=url, reason=reason) for url, reason in outcome.skipped]
    counts, ids = upsert_notices(session, notices)
    return ScrapeReport(
        source=request.source,
        created=counts.created,
        updated=counts.updated,
        unchanged=counts.unchanged,
        tender_ids=ids,
        skipped=skipped,
        blocked=blocked,
    )


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
