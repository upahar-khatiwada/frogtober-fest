"""Raw tender notices -> `tenders` rows (status `new`), upserted by source_url.

Both sources (the synthetic seed set and the live scraper) produce
`RawNotice`s. Only the raw text is stored; Scout extracts everything else.
"""

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from db.models import ComplianceItemRow, Match, Tender
from ingest.parse_docs import clean_text
from schemas import TenderStatus

# Columns filled from Scout's TenderRecord. Cleared when the raw text changes.
_DERIVED = ("title", "buyer", "deadline", "location", "record_json", "procurement_type", "method",
            "province", "district", "deadline_bs", "estimated_cost_npr", "language")


@dataclass(frozen=True)
class RawNotice:
    source_url: str
    raw_text: str


@dataclass
class UpsertCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


def upsert_notices(session: Session, notices: list[RawNotice]) -> tuple[UpsertCounts, list[int]]:
    """Insert new notices as `new`; leave identical ones (and their pipeline progress) alone.

    A notice whose raw text changed is reset to `new`: Scout output and the match and
    compliance rows derived from the old text are dropped. Proposals are kept (human work).
    """
    counts, ids = UpsertCounts(), []
    by_url: dict[str, RawNotice] = {}
    for notice in notices:  # last one wins if a source repeats a URL
        by_url[notice.source_url] = RawNotice(notice.source_url, clean_text(notice.raw_text))
    existing = {t.source_url: t for t in session.scalars(select(Tender).where(Tender.source_url.in_(by_url)))}
    for url, notice in by_url.items():
        tender = existing.get(url)
        if tender is None:
            tender = Tender(source_url=url, raw_text=notice.raw_text, status=TenderStatus.NEW.value)
            session.add(tender)
            counts.created += 1
        elif tender.raw_text == notice.raw_text:
            counts.unchanged += 1
        else:
            tender.raw_text = notice.raw_text
            tender.status = TenderStatus.NEW.value
            for column in _DERIVED:
                setattr(tender, column, None)
            tender.updated_at = func.now()
            session.execute(delete(Match).where(Match.tender_id == tender.id))
            session.execute(delete(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id))
            counts.updated += 1
        session.flush()
        ids.append(tender.id)
    session.commit()
    return counts, ids
