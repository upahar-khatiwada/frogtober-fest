"""Matching agent: TenderRecord + company profile + top-k KB chunks -> MatchResult (spec section 8.1).

Two halves, kept apart so a reader can tell code from judgement:

- **Deterministic** (`deterministic_signals`, hard rule 5): procurement type
  vs the profile's types, district/province served, estimated cost vs a
  multiple of average turnover, and the deadline in Nepal time. Each yields
  fit points, and a failure is a hard skip reason.
- **Model** (`assess`): the LLM fills `MatchAssessment`, a 0-100 semantic
  relevance score with short reasons, at temperature 0. It is told to judge
  scope fit only, because code owns everything above.

`combine` computes the final score and the pursue/skip decision in code. A
hard skip caps the score below the threshold, so skipped tenders always rank
below pursued ones. `run_matching` persists to `matches` and sets the tender
status `matched` or `skipped`; Compliance runs only on `matched`.
"""

import hashlib
import json
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from db.models import AgentRunRow, Company, Match, Tender
from db.search import ChunkHit, retrieve
from nepal.dates import NPT, days_left
from nepal.geography import DISTRICTS
from nepal.numbers import humanize_npr
from pipeline.llm import LLMClient, LLMError
from schemas import (CompanyProfile, MatchAssessment, MatchDecision, MatchResult, MatchSignal, ProcurementType, SignalSource,
                     Stage, TenderRecord, TenderStatus)

# Deterministic fit points; they sum to 100.
POINTS = {"procurement_type": 30, "geography": 30, "budget": 25, "deadline": 15}

# Statuses Matching may (re)run from (`failed` only with a Scout record, i.e. a failed Matching run).
# Later stages keep their match; re-matching them would skip past Compliance.
MATCHABLE = {TenderStatus.EXTRACTED, TenderStatus.MATCHED, TenderStatus.SKIPPED, TenderStatus.FAILED}

DETERMINISTIC_MODEL = "deterministic"  # agent_runs.model for a run that made no LLM call

SYSTEM_PROMPT = """You assess how relevant a public tender in Nepal is to one company's line of business.

Judge ONLY the semantic fit of the tender's scope (what is being procured, the kind of work, the skills and
experience it needs) against the company's sectors, services and knowledge-base evidence.
Do NOT consider the deadline, budget size, location, licence class or required documents: other code checks those.

Score 0-100:
- 85-100: the core work is exactly what the company does, with matching past projects in its knowledge base.
- 60-84: the work is within the company's sectors, but the evidence is thinner or the scope is partly outside.
- 30-59: related field, but the main work is something the company does not do.
- 0-29: a different line of business (e.g. medical equipment for a civil contractor), or the notice procures nothing
  (a cancellation or a corrigendum without scope).

Give 1-4 short reasons (one sentence each). When a reason rests on a knowledge-base excerpt, cite it as [chunk N].
Reply with JSON only."""

_CHUNK_CHARS = 700
_MAX_REQUIREMENTS = 10


# --- deterministic half ---------------------------------------------------------------

def average_turnover(company: CompanyProfile, years: int) -> int | None:
    """Mean of the `years` most recent fiscal years in the profile (fewer if fewer are recorded)."""
    recent = sorted(company.turnover, key=lambda t: t.fiscal_year_bs, reverse=True)[:years]
    return round(sum(t.amount_npr for t in recent) / len(recent)) if recent else None


def _signal(name: str, points: int, detail: str, hard_skip: bool = False) -> MatchSignal:
    return MatchSignal(name=name, source=SignalSource.DETERMINISTIC, points=points, max_points=POINTS[name],
                       hard_skip=hard_skip, detail=detail)


def _procurement_type(tender: TenderRecord, company: CompanyProfile) -> MatchSignal:
    full, kind = POINTS["procurement_type"], tender.procurement_type
    if not company.procurement_types:
        return _signal("procurement_type", full // 2, "company profile lists no procurement types, so type is not checked")
    wanted = ", ".join(t.value for t in company.procurement_types)
    if kind is ProcurementType.UNKNOWN:
        return _signal("procurement_type", full // 2, f"procurement type not stated in the notice (company bids on {wanted})")
    if kind in company.procurement_types:
        return _signal("procurement_type", full, f"procurement type {kind.value} is one the company bids on")
    return _signal("procurement_type", 0, f"procurement type {kind.value} is not one the company bids on ({wanted})", True)


def _geography(tender: TenderRecord, company: CompanyProfile) -> MatchSignal:
    full = POINTS["geography"]
    served = {d.casefold(): d for d in company.districts_served}
    served_provinces = {DISTRICTS[d][1] for d in company.districts_served if d in DISTRICTS}
    if company.province:
        served_provinces.add(company.province)
    if not served and not served_provinces:
        return _signal("geography", full // 2, "company profile lists no districts or province served, so location is not checked")
    if tender.district:
        if tender.district.casefold() in served:
            return _signal("geography", full, f"{tender.district} district is served by the company")
        if not served:  # profile has a province but no district list
            if tender.province in served_provinces:
                return _signal("geography", full // 2, f"{tender.district} is in {tender.province.value}, the company's province")
            return _signal("geography", 0, f"{tender.district} is outside the company's province", True)
        return _signal("geography", 0, f"{tender.district} district is not among the districts served "
                                       f"({', '.join(company.districts_served)})", True)
    if tender.province:
        if tender.province in served_provinces:
            return _signal("geography", full // 2, f"district not stated; {tender.province.value} province is served")
        return _signal("geography", 0, f"{tender.province.value} province has none of the districts served", True)
    return _signal("geography", full // 3, "location not stated in the notice")


def _budget(tender: TenderRecord, company: CompanyProfile, settings: Settings) -> MatchSignal:
    full, cap = POINTS["budget"], settings.match_max_cost_to_turnover
    avg = average_turnover(company, settings.match_turnover_years)
    cost = tender.estimated_cost_npr
    if cost is None:
        return _signal("budget", full * 2 // 5, "estimated cost not stated (or not confirmed) in the notice")
    if not avg:
        return _signal("budget", full * 2 // 5, f"estimated cost {humanize_npr(cost)}; no turnover in the profile to compare")
    ratio = cost / avg
    text = f"estimated cost {humanize_npr(cost)} is {ratio:.2f}x average annual turnover {humanize_npr(round(avg, -4))}"
    if ratio <= 1:
        return _signal("budget", full, f"{text} (within capacity)")
    if ratio <= cap:
        return _signal("budget", full // 2, f"{text} (stretch; limit {cap:g}x)")
    return _signal("budget", 0, f"{text} (above the {cap:g}x capacity limit)", True)


def _deadline(tender: TenderRecord, settings: Settings, now: datetime) -> MatchSignal:
    full = POINTS["deadline"]
    if tender.deadline_ad is None:
        return _signal("deadline", full // 3, "submission deadline not confirmed; check the notice")
    left = days_left(tender.deadline_ad, now)
    when = tender.deadline_ad.astimezone(NPT).strftime("%Y-%m-%d %H:%M NPT")
    if tender.deadline_ad <= now:
        return _signal("deadline", 0, f"deadline {when} has passed", True)
    if left < settings.match_tight_deadline_days:
        return _signal("deadline", full // 3, f"deadline {when}: only {left} day(s) left")
    return _signal("deadline", full, f"deadline {when}: {left} days left")


def deterministic_signals(tender: TenderRecord, company: CompanyProfile, *, settings: Settings | None = None,
                          now: datetime | None = None) -> list[MatchSignal]:
    settings = settings or get_settings()
    now = (now or datetime.now(NPT)).astimezone(NPT)
    return [
        _procurement_type(tender, company),
        _geography(tender, company),
        _budget(tender, company, settings),
        _deadline(tender, settings, now),
    ]


# --- model half -----------------------------------------------------------------------

def build_messages(tender: TenderRecord, company: CompanyProfile, chunks: Sequence[ChunkHit]) -> list[dict[str, str]]:
    reqs = [f"- {r.text}" for r in tender.requirements[:_MAX_REQUIREMENTS]]
    tender_text = "\n".join([
        f"Title: {tender.title}",
        f"Buyer: {tender.buyer}",
        f"Scope: {tender.scope}",
        f"Procurement type: {tender.procurement_type.value}; method: {tender.method.value}",
        "Requirements:" if reqs else "Requirements: (none extracted)",
        *reqs,
    ])
    company_text = "\n".join([
        f"Name: {company.name}",
        f"Sectors: {', '.join(company.sectors) or '(none listed)'}",
        f"Services: {company.services or '(none listed)'}",
    ])
    kb = "\n\n".join(f"[chunk {c.chunk_id}] ({c.doc_type.value}, {c.filename})\n{c.content[:_CHUNK_CHARS]}" for c in chunks)
    user = f"TENDER\n{tender_text}\n\nCOMPANY\n{company_text}\n\nKNOWLEDGE BASE EXCERPTS\n{kb or '(none retrieved)'}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def assess(client: LLMClient, tender: TenderRecord, company: CompanyProfile, chunks: Sequence[ChunkHit], *,
           tender_id: int | None = None) -> MatchAssessment:
    """One schema-constrained LLM call at temperature 0. Raises LLMError (agent_runs row already recorded)."""
    return client.chat(stage=Stage.MATCHING, messages=build_messages(tender, company, chunks), schema=MatchAssessment,
                       tender_id=tender_id)


# --- combination (code decides) ---------------------------------------------------------

def combine(signals: Sequence[MatchSignal], assessment: MatchAssessment | None, *, threshold: int, llm_weight: float,
            chunk_ids: Sequence[int] = ()) -> MatchResult:
    det = [s for s in signals if s.source is SignalSource.DETERMINISTIC]
    det_score = round(100 * sum(s.points for s in det) / (sum(s.max_points for s in det) or 1))
    skip_reasons = [s.detail for s in det if s.hard_skip]
    reasons = [f"[deterministic] {'SKIP: ' if s.hard_skip else ''}{s.detail}" for s in det]
    all_signals = list(det)

    if assessment is None:
        score = det_score
    else:
        score = round(llm_weight * assessment.score + (1 - llm_weight) * det_score)
        reasons += [f"[model] {r}" for r in assessment.reasons]
        all_signals.append(MatchSignal(name="semantic", source=SignalSource.MODEL, points=assessment.score, max_points=100,
                                       detail=f"model relevance score {assessment.score}/100"))
    if skip_reasons:
        score = max(0, min(score, threshold - 1))
    decision = MatchDecision.PURSUE if score >= threshold and not skip_reasons else MatchDecision.SKIP
    if decision is MatchDecision.SKIP and not skip_reasons:
        reasons.append(f"[deterministic] score {score} is below the threshold {threshold}")
    return MatchResult(
        score=score, reasons=reasons[:16], decision=decision, threshold=threshold, deterministic_score=det_score,
        semantic_score=assessment.score if assessment else None,
        llm_weight=llm_weight if assessment else None, skip_reasons=skip_reasons, signals=all_signals,
        chunk_ids=list(chunk_ids),
    )


def score_tender(tender: TenderRecord, company: CompanyProfile, chunks: Sequence[ChunkHit], *,
                 client: LLMClient | None, settings: Settings | None = None, now: datetime | None = None,
                 tender_id: int | None = None) -> MatchResult:
    """Score one tender for one company.

    The LLM is asked unless a deterministic rule already forces skip (and `match_llm_on_hard_skip` is off), or
    `client` is None (deterministic-only scoring, used by the offline metric). Raises LLMError if the model call
    fails twice; the caller marks the tender `failed`.
    """
    settings = settings or get_settings()
    signals = deterministic_signals(tender, company, settings=settings, now=now)
    hard = any(s.hard_skip for s in signals)
    assessment = None
    if client is not None and (not hard or settings.match_llm_on_hard_skip):
        assessment = assess(client, tender, company, chunks, tender_id=tender_id)
    return combine(signals, assessment, threshold=settings.match_threshold, llm_weight=settings.match_llm_weight,
                   chunk_ids=[c.chunk_id for c in chunks] if assessment else [])


# --- DB write -------------------------------------------------------------------------

def retrieval_query(tender: TenderRecord) -> str:
    return f"{tender.title}. {tender.scope}"


def load_company(session: Session) -> tuple[Company, CompanyProfile] | None:
    company = session.scalars(select(Company).order_by(Company.id).limit(1)).first()
    return (company, CompanyProfile.model_validate(company.profile_json)) if company else None


def _record_code_run(session: Session, tender: Tender, payload: dict[str, Any], started: float, *,
                     output: MatchResult | None = None, error: str | None = None) -> None:
    """agent_runs row for a Matching run that made no LLM call (hard rule 9); the client records the others."""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    session.add(AgentRunRow(
        tender_id=tender.id, stage=Stage.MATCHING.value, model=DETERMINISTIC_MODEL, input_hash=digest,
        output_json=output.model_dump(mode="json") if output else None,
        latency_ms=int((time.perf_counter() - started) * 1000), ok=error is None, attempts=1, error=error,
    ))


def run_matching(session: Session, client: LLMClient, tender: Tender, *, settings: Settings | None = None,
                 now: datetime | None = None) -> MatchResult | None:
    """Match one extracted tender: replace its `matches` row, set status matched/skipped (or failed on LLMError)."""
    settings = settings or get_settings()
    if TenderStatus(tender.status) not in MATCHABLE or tender.record_json is None:
        raise ValueError(f"tender {tender.id} is {tender.status}; Matching runs on extracted/matched/skipped tenders")
    loaded = load_company(session)
    if loaded is None:
        raise ValueError("no company profile; POST /company first")
    company_row, company = loaded
    record = TenderRecord.model_validate(tender.record_json)
    started = time.perf_counter()
    payload = {"tender": tender.record_json, "company": company_row.profile_json, "now": now, "stage": "matching",
               "settings": settings.model_dump(include={k for k in Settings.model_fields if k.startswith("match_")})}

    signals = deterministic_signals(record, company, settings=settings, now=now)
    will_ask = not any(s.hard_skip for s in signals) or settings.match_llm_on_hard_skip
    chunks: list[ChunkHit] = []
    if will_ask:
        try:
            chunks = retrieve(session, client, retrieval_query(record), settings.match_top_k, company_id=company_row.id)
        except LLMError as exc:  # embedding call failed: no chat call happened, so record the run here
            _record_code_run(session, tender, payload, started, error=f"KB retrieval failed: {exc}")
            return _fail(session, tender)
    try:
        result = score_tender(record, company, chunks, client=client, settings=settings, now=now, tender_id=tender.id)
    except LLMError:  # the client already recorded the failed agent_runs row
        return _fail(session, tender)

    if result.semantic_score is None:
        _record_code_run(session, tender, payload, started, output=result)
    session.execute(delete(Match).where(Match.tender_id == tender.id))
    session.add(Match(tender_id=tender.id, score=result.score, reasons=result.model_dump(mode="json"),
                      decision=result.decision.value))
    tender.status = (TenderStatus.MATCHED if result.decision is MatchDecision.PURSUE else TenderStatus.SKIPPED).value
    tender.updated_at = func.now()
    session.commit()
    return result


def _fail(session: Session, tender: Tender) -> None:
    session.execute(delete(Match).where(Match.tender_id == tender.id))
    tender.status = TenderStatus.FAILED.value
    tender.updated_at = func.now()
    session.commit()
    return None


def match_extracted_tenders(session: Session, client: LLMClient, tender_ids: list[int] | None = None, *,
                            settings: Settings | None = None, now: datetime | None = None) -> dict[int, MatchResult | None]:
    """Run Matching on every `extracted` tender (or just these ids, if still `extracted`)."""
    query = select(Tender).where(Tender.status == TenderStatus.EXTRACTED.value).order_by(Tender.id)
    if tender_ids is not None:
        query = query.where(Tender.id.in_(tender_ids))
    return {t.id: run_matching(session, client, t, settings=settings, now=now) for t in session.scalars(query)}
