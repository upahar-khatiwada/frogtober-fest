"""Review agent: proposal + requirements -> ReviewReport (spec sections 8.1, 10.3). Temperature 0 (hard rule 7).

Code and model split the work, as in every stage:

- **Deterministic checks (code, `run_checks`, hard rule 5):** every mandatory requirement is answered by a drafted
  section (not a `no_kb_material` stub); no unresolved placeholder or masked figure is left in the text; the bid
  security is stated when the notice asks for one; the submission deadline has not passed (NPT); every section cites
  the KB (hard rule 8). Each failed check becomes a gap tied to its requirement or section.
- **Model judgement (`review_proposal`):** one `ReviewAssessment` call scores completeness, relevance and compliance
  (0-100) and lists gaps. Its schema is narrowed per proposal (`assessment_schema`) so a gap can only name a real
  section key or requirement index; anything else is invalid output (one retry, then the stage fails).
- **Verdict (code, `decide_verdict`):** `fail` on a failed hard check (deadline passed, a mandatory requirement
  unanswered) or any score below REVIEW_FAIL_BELOW_SCORE; `needs_work` on a failed soft check, a score below
  REVIEW_PASS_MIN_SCORE or a hard model gap; otherwise `pass`. A `fail` cannot be approved.

`run_review` (the orchestrator's drafted -> reviewed step) reviews the latest version, and when the verdict is not
`pass` and REVIEW_AUTO_REVISE is on, feeds the gaps back to the Proposal agent once (`agents.proposal.revise_proposal`)
and reviews the revision. Then it stops: the person decides. The human gate is `approve_proposal`
(POST /proposals/{id}/approve): it needs a review, a verdict other than `fail`, and an open after the review.
"""

import hashlib
import json
import re
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, create_model
from sqlalchemy import func
from sqlalchemy.orm import Session

from agents.compliance import RetrievalError
from agents.proposal import format_date, latest_proposal, revise_proposal
from config import Settings, get_settings
from db.models import AgentRunRow, ProposalRow, Tender
from nepal.dates import NPT
from nepal.numbers import format_npr
from pipeline.llm import LLMClient, LLMError
from schemas import (DocType, GapSource, ProposalLanguage, ProposalSection, ProposalStatus, ReviewAssessment, ReviewCheck,
                     ReviewCheckId, ReviewGap, ReviewGapDraft, ReviewReport, ReviewScores, ReviewVerdict,
                     SectionFlagKind, Severity, Stage, TenderRecord, TenderStatus)

C = ReviewCheckId
DETERMINISTIC_MODEL = "deterministic"  # agent_runs.model for the checks + verdict row (no LLM call)
HUMAN_MODEL = "human"  # agent_runs.model for a person's action (approval)
REVIEWABLE = {TenderStatus.DRAFTED}

# --- deterministic checks -------------------------------------------------------------------------------------

# Left in the text by Proposal (agents.proposal.resolve_placeholders / mask_unsourced) or by a model.
UNRESOLVED = re.compile(
    r"\[(?:MISSING|UNKNOWN|UNVERIFIED):[^\]]*\]|⟦unsourced:[^⟧]*⟧|\{\{[^}]*\}\}"
    r"|\[(?:insert|enter|add|fill|to be (?:filled|confirmed|added)|tbd)\b[^\]]*\]|\bTBD\b|\bX{3,}\b")
BID_SECURITY = re.compile(r"bid\s*(?:security|bond|guarantee)|tender\s*security|बोलपत्र\s*(?:जमानत|सुरक्षण)|धरौटी|जमानत",
                          re.I)
# Where a missing bid-security statement belongs, in order of preference.
_BID_SECURITY_SECTIONS = ("declarations", "cover_letter", "bidder_info")


def bid_security_required(record: TenderRecord) -> bool:
    return record.bid_security is not None or any(
        d.doc_type is DocType.BID_SECURITY and d.mandatory for d in record.required_docs)


def _bid_security_amount(record: TenderRecord) -> int | None:
    if record.bid_security_due and record.bid_security_due.amount_npr is not None:
        return record.bid_security_due.amount_npr
    return record.bid_security.amount_npr if record.bid_security else None


def _check(check: ReviewCheckId, passed: bool, severity: Severity, detail: str) -> ReviewCheck:
    return ReviewCheck(check=check, passed=passed, severity=severity, detail=detail)


def _gap(check: ReviewCheckId, issue: str, severity: Severity, *, section: str | None = None,
         requirement: int | None = None, suggestion: str | None = None) -> ReviewGap:
    return ReviewGap(source=GapSource.CHECK, check=check, section_key=section, requirement_index=requirement,
                     issue=issue, severity=severity, suggestion=suggestion)


def run_checks(record: TenderRecord, sections: Sequence[ProposalSection], now: datetime
               ) -> tuple[list[ReviewCheck], list[ReviewGap]]:
    """The deterministic half of Review: five checks, and a gap for each thing that failed."""
    checks: list[ReviewCheck] = []
    gaps: list[ReviewGap] = []
    hard, soft = Severity.HARD, Severity.SOFT

    # 1. Every mandatory requirement is answered by a section that was actually drafted.
    routed = {i: s.key for s in sections for i in s.requirement_indices}
    drafted = {i for s in sections if not any(f.kind is SectionFlagKind.NO_KB_MATERIAL for f in s.flags)
               for i in s.requirement_indices}
    mandatory = [i for i, r in enumerate(record.requirements) if r.mandatory]
    unanswered = [i for i in mandatory if i not in drafted]
    for i in unanswered:
        where = routed.get(i)
        why = f" (section '{where}' found no knowledge-base material)" if where else " (no section answers it)"
        gaps.append(_gap(C.MANDATORY_ADDRESSED, f"Mandatory requirement not answered{why}: {record.requirements[i].text}",
                         hard, section=where, requirement=i,
                         suggestion="Upload a document that shows the company meets it, then regenerate the proposal."))
    checks.append(_check(C.MANDATORY_ADDRESSED, not unanswered, hard,
                         f"{len(mandatory) - len(unanswered)} of {len(mandatory)} mandatory requirements answered"
                         if mandatory else "the notice lists no mandatory requirements"))

    # 2. No unresolved placeholder, masked figure or template blank.
    marked = {s.key: list(dict.fromkeys(m.group(0) for m in UNRESOLVED.finditer(s.body))) for s in sections}
    marked = {k: v for k, v in marked.items() if v}
    for key, markers in marked.items():
        gaps.append(_gap(C.NO_PLACEHOLDERS, f"Unresolved in the text: {', '.join(markers[:6])}", soft, section=key,
                         suggestion="Add the missing values to the company profile or the knowledge base and "
                                    "regenerate; never type a figure without a source."))
    checks.append(_check(C.NO_PLACEHOLDERS, not marked, soft,
                         f"unresolved text in {len(marked)} section(s): {', '.join(marked)}" if marked
                         else "no placeholders or masked figures left"))

    # 3. The bid security is stated when the notice asks for one.
    if not bid_security_required(record):
        checks.append(_check(C.BID_SECURITY_STATED, True, soft, "the notice asks for no bid security"))
    elif any(BID_SECURITY.search(s.body) for s in sections):
        checks.append(_check(C.BID_SECURITY_STATED, True, soft, "the proposal states the bid security"))
    else:
        keys = [s.key for s in sections]
        target = next((k for k in _BID_SECURITY_SECTIONS if k in keys), keys[0] if keys else None)
        amount = _bid_security_amount(record)
        what = f"a bid security of {format_npr(amount)}" if amount is not None else "the bid security"
        gaps.append(_gap(C.BID_SECURITY_STATED, "The notice requires a bid security, but no section mentions it.", soft,
                         section=target, suggestion=f"State that {what} is enclosed, as the notice asks."))
        checks.append(_check(C.BID_SECURITY_STATED, False, soft, f"bid security required ({what}) but not stated"))

    # 4. The submission deadline has not passed (NPT). Unknown deadline: confirm it by hand.
    if record.deadline_ad is None:
        gaps.append(_gap(C.DEADLINE_NOT_PASSED, "The submission deadline could not be confirmed from the notice.", soft,
                         suggestion="Check the deadline in the notice before approving."))
        checks.append(_check(C.DEADLINE_NOT_PASSED, False, soft, "deadline unknown"))
    else:
        when = format_date(record.deadline_ad, ProposalLanguage.EN, with_bs=True)
        passed = record.deadline_ad > now
        if not passed:
            gaps.append(_gap(C.DEADLINE_NOT_PASSED, f"The submission deadline has passed: {when}.", hard,
                             suggestion="This bid can no longer be submitted."))
        checks.append(_check(C.DEADLINE_NOT_PASSED, passed, hard, f"deadline {when}" + ("" if passed else " has passed")))

    # 5. Every section cites the knowledge base (hard rule 8).
    uncited = [s.key for s in sections if not s.grounded]
    for key in uncited:
        gaps.append(_gap(C.SECTIONS_CITED, "The section cites no knowledge-base chunk; its claims are unsupported.", soft,
                         section=key, suggestion="Check every claim against the company's documents, or upload them."))
    checks.append(_check(C.SECTIONS_CITED, not uncited, soft,
                         f"{len(sections) - len(uncited)} of {len(sections)} sections cite the knowledge base"))
    return checks, gaps


def decide_verdict(scores: ReviewScores, checks: Sequence[ReviewCheck], gaps: Sequence[ReviewGap], *,
                   pass_min: int, fail_below: int) -> tuple[ReviewVerdict, list[str]]:
    """The verdict, in code: fail > needs_work > pass. Every reason names its source."""
    failing = [f"[check] {c.check.value}: {c.detail}" for c in checks if not c.passed and c.severity is Severity.HARD]
    if scores.lowest < fail_below:
        failing.append(f"[model] lowest score {scores.lowest} is below {fail_below}")
    if failing:
        return ReviewVerdict.FAIL, failing
    work = [f"[check] {c.check.value}: {c.detail}" for c in checks if not c.passed]
    if scores.lowest < pass_min:
        work.append(f"[model] lowest score {scores.lowest} is below {pass_min}")
    if hard_gaps := [g for g in gaps if g.source is GapSource.MODEL and g.severity is Severity.HARD]:
        work.append(f"[model] {len(hard_gaps)} hard gap(s) reported")
    if work:
        return ReviewVerdict.NEEDS_WORK, work
    return ReviewVerdict.PASS, [f"every check passed and every score is at least {pass_min}"]


# --- the model call -------------------------------------------------------------------------------------------

SYSTEM_PROMPT = """You review a draft bid/proposal that a company in Nepal will submit for a public tender, before a person approves it.

Score each from 0 to 100:
- completeness: every listed tender requirement is answered in the section shown for it, and each section does what its title says.
- relevance: the text is specific to this tender's scope, site and procuring entity, not generic.
- compliance: the text is consistent with the requirements and claims nothing that falls short of them (e.g. a lower licence class, smaller experience or capacity than required).

List gaps, at most 12, most important first. Each gap is about ONE requirement (requirement_index = the n of [R n]) and/or ONE section (section_key).
Use severity "hard" only if the bid would likely be judged non-responsive because of the gap.
Code already checks these; do not report them: [MISSING]/[UNKNOWN]/[UNVERIFIED]/⟦unsourced⟧ markers, citations, the submission deadline, and whether the bid security is mentioned.
Judge only from the text shown; do not assume documents or facts it does not mention.
Reply with JSON only."""

_SECTION_CHARS = 1000


def assessment_schema(section_keys: Sequence[str], n_requirements: int) -> type[ReviewAssessment]:
    """ReviewAssessment narrowed to this proposal: section_key must be one of its keys, requirement_index in range."""
    key_type = Literal[tuple(section_keys)] | None if section_keys else None  # type: ignore[valid-type]
    index_type = Annotated[int, Field(ge=0, le=n_requirements - 1)] | None if n_requirements else None
    gap = create_model(
        "ReviewGapDraft", __base__=ReviewGapDraft,
        requirement_index=(index_type, Field(None, description="n of the [R n] requirement the gap is about; null if none.")),
        section_key=(key_type, Field(None, description="Key of the section the gap is in; null if none.")))
    return create_model("ReviewAssessment", __base__=ReviewAssessment,
                        gaps=(list[gap], Field(default_factory=list, max_length=12)))


def build_messages(record: TenderRecord, sections: Sequence[ProposalSection]) -> list[dict[str, str]]:
    answered = {i: s.key for s in sections for i in s.requirement_indices}
    reqs = "\n".join(
        f"[R {i}] ({'mandatory' if r.mandatory else 'optional'}, {r.category.value}) {r.text}"
        f" -> answered in: {answered.get(i, 'no section')}" for i, r in enumerate(record.requirements)) or "(none listed)"
    body = "\n\n".join(
        f"### {s.key}: {s.title} (cites the knowledge base: {'yes' if s.grounded else 'no'})\n{s.body[:_SECTION_CHARS]}"
        for s in sections)
    user = (f"TENDER\nTitle: {record.title}\nProcuring entity: {record.buyer}\nType: {record.procurement_type.value}; "
            f"method: {record.method.value}\nScope: {record.scope}\n\n"
            f"TENDER REQUIREMENTS\n{reqs}\n\nPROPOSAL SECTIONS (section_key: title)\n{body}")
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def review_proposal(client: LLMClient, record: TenderRecord, sections: Sequence[ProposalSection], *, now: datetime,
                    settings: Settings | None = None, tender_id: int | None = None) -> ReviewReport:
    """Checks (code) + one ReviewAssessment call (model) -> ReviewReport with the verdict decided in code.

    Raises LLMError (its agent_runs row is already recorded by the client).
    """
    settings = settings or get_settings()
    checks, gaps = run_checks(record, sections, now)
    schema = assessment_schema([s.key for s in sections], len(record.requirements))
    assessment = client.chat(stage=Stage.REVIEW, messages=build_messages(record, sections), schema=schema,
                             tender_id=tender_id)
    gaps += [ReviewGap(source=GapSource.MODEL, requirement_index=g.requirement_index, section_key=g.section_key,
                       issue=g.issue, severity=g.severity, suggestion=g.suggestion) for g in assessment.gaps]
    scores = assessment.scores
    verdict, reasons = decide_verdict(scores, checks, gaps, pass_min=settings.review_pass_min_score,
                                      fail_below=settings.review_fail_below_score)
    return ReviewReport(scores=scores, checks=checks, gaps=gaps, uncited_sections=[s.key for s in sections if not s.grounded],
                        verdict=verdict, verdict_reasons=reasons, pass_min_score=settings.review_pass_min_score,
                        fail_below_score=settings.review_fail_below_score)


def revision_feedback(report: ReviewReport, sections: Sequence[ProposalSection]) -> dict[str, list[str]]:
    """Gaps per section for the revision pass. A requirement gap goes to the section that answers it.

    The deadline check has no section and a redraft cannot fix it, so it is never fed back.
    """
    answered = {i: s.key for s in sections for i in s.requirement_indices}
    feedback: dict[str, list[str]] = {}
    for gap in report.gaps:
        key = gap.section_key or (answered.get(gap.requirement_index) if gap.requirement_index is not None else None)
        if key is None or gap.check is C.DEADLINE_NOT_PASSED:
            continue
        feedback.setdefault(key, []).append(gap.issue + (f" Fix: {gap.suggestion}" if gap.suggestion else ""))
    return feedback


# --- DB -------------------------------------------------------------------------------------------------------


def _record_code_run(session: Session, tender: Tender, payload: dict[str, Any], started: float, *,
                     output: dict[str, Any] | None = None, error: str | None = None, model: str = DETERMINISTIC_MODEL,
                     ) -> None:
    """agent_runs row for the checks + verdict, a failed KB retrieval, or a person's action (hard rule 9)."""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    session.add(AgentRunRow(
        tender_id=tender.id, stage=Stage.REVIEW.value, model=model, input_hash=digest, output_json=output,
        latency_ms=int((time.perf_counter() - started) * 1000), ok=error is None, attempts=1, error=error,
    ))


def _store(session: Session, tender: Tender, row: ProposalRow, report: ReviewReport, now: datetime, started: float) -> None:
    row.review_json = report.model_dump(mode="json")
    row.status = ProposalStatus.REVIEWED.value
    row.reviewed_at = now
    _record_code_run(session, tender, {"proposal_id": row.id, "version": row.version, "stage": "review", "now": now},
                     started, output={"proposal_id": row.id, "version": row.version, "verdict": report.verdict.value,
                                      "verdict_reasons": report.verdict_reasons,
                                      "checks": [c.model_dump(mode="json") for c in report.checks]})


def run_review(session: Session, client: LLMClient, tender: Tender, *, settings: Settings | None = None,
               now: datetime | None = None) -> ReviewReport | None:
    """Review the latest version of a drafted tender; maybe revise once; set `reviewed` (`failed` on LLMError).

    Returns the report of the version the person should look at (the revision, if one was made).
    """
    settings = settings or get_settings()
    if TenderStatus(tender.status) not in REVIEWABLE or tender.record_json is None:
        raise ValueError(f"tender {tender.id} is {tender.status}; Review runs on drafted tenders")
    row = latest_proposal(session, tender.id)
    if row is None:
        raise ValueError(f"tender {tender.id} has no proposal to review")
    now = now or datetime.now(NPT)
    record = TenderRecord.model_validate(tender.record_json)
    started = time.perf_counter()
    try:
        sections = [ProposalSection.model_validate(s) for s in row.sections]
        report = review_proposal(client, record, sections, now=now, settings=settings, tender_id=tender.id)
        _store(session, tender, row, report, now, started)
        if settings.review_auto_revise and report.verdict is not ReviewVerdict.PASS:
            revised = revise_proposal(session, client, tender, row, revision_feedback(report, sections),
                                      settings=settings, now=now)
            if revised is not None:
                new_row, keys = revised
                started = time.perf_counter()
                new_sections = [ProposalSection.model_validate(s) for s in new_row.sections]
                second = review_proposal(client, record, new_sections, now=now, settings=settings, tender_id=tender.id)
                report = second.model_copy(update={"revision_of": row.version, "revised_sections": keys,
                                                   "previous_verdict": report.verdict})
                _store(session, tender, new_row, report, now, started)
    except LLMError as exc:
        # Nothing partial is kept (the first review, a half-made revision). A chat failure is already in agent_runs
        # (client); an embedding failure during the revision is not, so record it here.
        session.rollback()
        if isinstance(exc, RetrievalError):
            _record_code_run(session, tender, {"stage": "review", "proposal_id": row.id}, started,
                             error=f"KB retrieval failed: {exc}")
        tender.status = TenderStatus.FAILED.value
        tender.updated_at = func.now()
        session.commit()
        return None
    tender.status = TenderStatus.REVIEWED.value
    tender.updated_at = func.now()
    session.commit()
    return report


# --- the human gate -------------------------------------------------------------------------------------------


def mark_opened(session: Session, row: ProposalRow, now: datetime) -> ProposalRow:
    """A person opened this version (the proposal page calls POST /proposals/{id}/open when it shows it)."""
    row.opened_at = now
    session.commit()
    return row


def approval_blockers(session: Session, row: ProposalRow) -> list[str]:
    """Why this version cannot be approved now (empty = it can)."""
    from pipeline.orchestrator import active_run  # the orchestrator imports this module

    tender = session.get(Tender, row.tender_id)
    if row.status == ProposalStatus.APPROVED.value:
        return [f"version {row.version} is already approved"]
    if row.review_json is None:
        return [f"version {row.version} has not been reviewed; run the Review stage first"]
    blockers = []
    report = ReviewReport.model_validate(row.review_json)
    if report.verdict is ReviewVerdict.FAIL:
        blockers.append("the review verdict is fail: " + "; ".join(report.verdict_reasons))
    if row.opened_at is None or (row.reviewed_at is not None and row.opened_at < row.reviewed_at):
        blockers.append(f"version {row.version} has not been opened since its review; open it "
                        f"(POST /proposals/{row.id}/open) and read it before approving")
    if tender.status != TenderStatus.REVIEWED.value:
        blockers.append(f"tender {tender.id} is {tender.status}; only a reviewed tender can be approved")
    if active_run(session, tender.id) is not None:
        blockers.append(f"tender {tender.id} has a pipeline run in progress")
    return blockers


def approve_proposal(session: Session, row: ProposalRow, *, approved_by: str, note: str | None, now: datetime
                     ) -> ProposalRow:
    """The human reviewed -> approved edge. Raises ValueError (-> 409) with every blocker. Writes an audit row."""
    if blockers := approval_blockers(session, row):
        raise ValueError("; ".join(blockers))
    tender = session.get(Tender, row.tender_id)
    report = ReviewReport.model_validate(row.review_json)
    row.status, row.approved_at, row.approved_by, row.approval_note = ProposalStatus.APPROVED.value, now, approved_by, note
    tender.status = TenderStatus.APPROVED.value
    tender.updated_at = func.now()
    action = {"action": "approve", "proposal_id": row.id, "version": row.version, "verdict": report.verdict.value,
              "approved_by": approved_by, "note": note, "approved_at": now.isoformat(),
              "opened_at": row.opened_at.isoformat() if row.opened_at else None,
              "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}
    _record_code_run(session, tender, action, time.perf_counter(), output=action, model=HUMAN_MODEL)
    session.commit()
    return row
