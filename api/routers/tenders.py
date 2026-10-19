"""Tender endpoints (spec section 10.2).

Implemented: POST /tenders/scrape, GET /tenders (ranked, filtered), GET /tenders/{id},
POST /tenders/{id}/analyze (Matching; Compliance once it lands). The proposal route is a
stub that declares its response model so the OpenAPI schema (web/'s `gen:api`) carries it.
"""

from datetime import datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeVar

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import Settings
from db.models import Match, Tender
from deps import get_kankai_fetcher, get_llm_client, get_now, get_seed_dir, get_session, get_settings
from ingest.notices import upsert_notices
from ingest.scraper import PoliteFetcher, scrape_kankai
from ingest.seed_tenders import SeedDataError, load_seed_notices
from nepal.dates import NPT, ad_to_bs, days_left, format_bs
from nepal.geography import normalize_location
from pipeline import orchestrator
from pipeline.llm import LLMClient
from schemas import (BuyerLevel, DeadlineView, MatchDecision, MatchResult, NoticeLanguage, ProcurementMethod, ProcurementType,
                     Proposal, Province, ScrapeReport, ScrapeRequest, SkippedNotice, TenderDetail, TenderListItem,
                     TenderRecord, TenderSource, TenderStatus)

router = APIRouter(prefix="/tenders", tags=["tenders"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."
_501 = {status.HTTP_501_NOT_IMPLEMENTED: {"description": "Not implemented yet"}}

E = TypeVar("E", bound=StrEnum)


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


def deadline_view(deadline: datetime | None, now: datetime) -> DeadlineView | None:
    """AD + BS + days left, all from nepal.dates (lookup-table BS, NPT clock)."""
    if deadline is None:
        return None
    local = deadline.astimezone(NPT)
    bs = ad_to_bs(local.date())
    return DeadlineView(ad=local, ad_date=local.date(), bs=bs.iso(), bs_long=format_bs(bs, long=True),
                        bs_ne=format_bs(bs, long=True, ne=True), days_left=days_left(local, now), passed=local <= now)


def _enum_or_none(enum: type[E], value: str | None) -> E | None:
    try:
        return enum(value) if value is not None else None
    except ValueError:
        return None


def _match_of(session: Session, tender_id: int) -> Match | None:
    return session.scalars(select(Match).where(Match.tender_id == tender_id).order_by(Match.id.desc()).limit(1)).first()


def _detail(tender: Tender, match: Match | None, now: datetime) -> TenderDetail:
    return TenderDetail(
        id=tender.id,
        source_url=tender.source_url,
        status=TenderStatus(tender.status),
        deadline=tender.deadline,
        deadline_view=deadline_view(tender.deadline, now),
        record=TenderRecord.model_validate(tender.record_json) if tender.record_json else None,
        match=MatchResult.model_validate(match.reasons) if match else None,
    )


def _list_item(rank: int, tender: Tender, match: Match | None, now: datetime) -> TenderListItem:
    record = tender.record_json or {}
    first_line = (tender.raw_text or "").strip().split("\n", 1)[0][:200]
    return TenderListItem(
        rank=rank,
        id=tender.id,
        status=TenderStatus(tender.status),
        title=tender.title or first_line or None,
        buyer=tender.buyer,
        buyer_level=_enum_or_none(BuyerLevel, record.get("buyer_level")),
        procurement_type=_enum_or_none(ProcurementType, tender.procurement_type),
        method=_enum_or_none(ProcurementMethod, tender.method),
        province=_enum_or_none(Province, tender.province),
        district=tender.district,
        language=_enum_or_none(NoticeLanguage, tender.language),
        estimated_cost_npr=tender.estimated_cost_npr,
        deadline=deadline_view(tender.deadline, now),
        score=match.score if match else None,
        decision=MatchDecision(match.decision) if match else None,
        reasons=list(match.reasons.get("reasons", [])) if match else [],
        needs_review=bool(record.get("needs_review", False)),
        source_url=tender.source_url,
    )


@router.get("")
def list_tenders(
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(get_now)],
    procurement_type: ProcurementType | None = None,
    method: ProcurementMethod | None = None,
    province: Province | None = None,
    district: Annotated[str | None, Query(description="English or Nepali name; normalised to the canonical district.")] = None,
    buyer_level: BuyerLevel | None = None,
    min_score: Annotated[int | None, Query(ge=0, le=100, description="Only matched tenders scoring at least this.")] = None,
    deadline_within_days: Annotated[
        int | None, Query(ge=0, le=365, description="Deadline not passed and at most N calendar days away (NPT).")
    ] = None,
    language: NoticeLanguage | None = None,
    decision: MatchDecision | None = None,
    status_: Annotated[TenderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TenderListItem]:
    """Ranked list: match score (high first), then deadline (soonest first). Unscored tenders come last."""
    stmt = select(Tender, Match).outerjoin(Match, Match.tender_id == Tender.id)
    if procurement_type:
        stmt = stmt.where(Tender.procurement_type == procurement_type.value)
    if method:
        stmt = stmt.where(Tender.method == method.value)
    if province:
        stmt = stmt.where(Tender.province == province.value)
    if district:
        canonical = normalize_location(district).district or district.strip()
        stmt = stmt.where(func.lower(Tender.district) == canonical.lower())
    if buyer_level:
        stmt = stmt.where(Tender.record_json["buyer_level"].astext == buyer_level.value)
    if min_score is not None:
        stmt = stmt.where(Match.score >= min_score)
    if deadline_within_days is not None:
        local = now.astimezone(NPT)
        day_end = datetime.combine(local.date() + timedelta(days=deadline_within_days + 1), time(0), tzinfo=NPT)
        stmt = stmt.where(Tender.deadline > local, Tender.deadline < day_end)
    if language:
        stmt = stmt.where(Tender.language == language.value)
    if decision:
        stmt = stmt.where(Match.decision == decision.value)
    if status_:
        stmt = stmt.where(Tender.status == status_.value)
    stmt = stmt.order_by(Match.score.desc().nulls_last(), Tender.deadline.asc().nulls_last(), Tender.id)
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return [_list_item(rank, tender, match, now) for rank, (tender, match) in enumerate(rows, start=offset + 1)]


@router.get("/{tender_id}", responses={status.HTTP_404_NOT_FOUND: {"description": "No such tender"}})
def get_tender(
    tender_id: int,
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(get_now)],
) -> TenderDetail:
    """Tender detail and match result (the compliance report lands with the Compliance agent)."""
    tender = session.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No tender {tender_id}")
    return _detail(tender, _match_of(session, tender_id), now)


@router.post(
    "/{tender_id}/analyze",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No such tender"},
        status.HTTP_409_CONFLICT: {"description": "Not extracted yet, already past Matching, or no company profile"},
    },
)
def analyze_tender(
    tender_id: int,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> TenderDetail:
    """Run Matching, then Compliance if pursued. A model failure returns the tender with status `failed`."""
    tender = session.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No tender {tender_id}")
    try:
        orchestrator.analyze_tender(session, client, tender, settings=settings, now=now)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _detail(tender, _match_of(session, tender_id), now)


@router.post("/{tender_id}/proposal", responses=_501)
def generate_proposal(tender_id: int) -> Proposal:
    """Run Proposal and Review."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
