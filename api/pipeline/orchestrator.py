"""Pipeline orchestrator: the tender status state machine (spec section 10.3).

new -> extracted -> matched -> checked -> drafted -> reviewed -> approved
             branches: skipped (match), blocked (hard compliance fail), failed (LLM output invalid twice)

Every stage writes its own agent_runs rows (hard rule 9): through the LLM
client's recorder, or the agent itself for code-only work (the Matching
pre-filters, the Compliance rules layer).

Implemented so far: Matching then Compliance (`analyze_tender`). A tender
that Matching skips never reaches Compliance. A blocked tender reaches
Proposal only through an explicit override (`agents.compliance.override_block`,
gated by `agents.compliance.proposal_allowed`). TODO (next prompts): Proposal,
then Review verdict "fail" -> one revision pass.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from agents.compliance import run_compliance
from agents.matching import run_matching
from config import Settings
from db.models import ComplianceItemRow, Tender
from pipeline.llm import LLMClient
from schemas import MatchResult, TenderStatus

ComplianceStep = Callable[[Session, LLMClient, Tender], object]


def _default_compliance(settings: Settings | None, now: datetime | None) -> ComplianceStep:
    return lambda session, client, tender: run_compliance(session, client, tender, settings=settings, now=now)


def analyze_tender(session: Session, client: LLMClient, tender: Tender, *, compliance: ComplianceStep | None = None,
                   settings: Settings | None = None, now: datetime | None = None) -> MatchResult | None:
    """POST /tenders/{id}/analyze: Matching, then Compliance only if the tender was `matched` (pursue).

    Re-running on a checked/blocked tender (e.g. after uploading a renewed document) re-matches and re-checks.
    If Matching no longer pursues it, its old compliance items are dropped as stale.
    """
    compliance = compliance or _default_compliance(settings, now)
    result = run_matching(session, client, tender, settings=settings, now=now, rematch=True)
    if tender.status == TenderStatus.MATCHED.value:
        compliance(session, client, tender)
    else:
        session.execute(delete(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id))
        session.commit()
    return result
