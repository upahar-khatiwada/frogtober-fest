"""Pipeline orchestrator: the tender status state machine (spec section 10.3).

new -> extracted -> matched -> checked -> drafted -> reviewed -> approved
             branches: skipped (match), blocked (hard compliance fail), failed (LLM output invalid twice)

Every stage writes its own agent_runs rows (hard rule 9): through the LLM
client's recorder, or `agents.matching` for a code-only Matching run.

Implemented so far: Matching (`analyze_tender`). A tender that Matching
skips never reaches Compliance. TODO (next prompts): Compliance, then
blocked -> no Proposal unless the user overrides; Review verdict "fail" ->
one revision pass.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from agents.matching import run_matching
from config import Settings
from db.models import Tender
from pipeline.llm import LLMClient
from schemas import MatchResult, TenderStatus

ComplianceStep = Callable[[Session, LLMClient, Tender], object]


def analyze_tender(session: Session, client: LLMClient, tender: Tender, *, compliance: ComplianceStep | None = None,
                   settings: Settings | None = None, now: datetime | None = None) -> MatchResult | None:
    """POST /tenders/{id}/analyze: Matching, then Compliance only if the tender was `matched` (pursue).

    `compliance` is None until the Compliance agent lands; a `matched` tender then stays `matched`.
    """
    result = run_matching(session, client, tender, settings=settings, now=now)
    if compliance is not None and tender.status == TenderStatus.MATCHED.value:
        compliance(session, client, tender)
    return result
