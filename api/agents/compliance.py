"""Compliance agent: requirements + company profile + documents -> ComplianceReport (spec section 8.1).

Two layers, kept apart so a reader can tell code from judgement:

- **Layer 1, rules** (`nepal.rules.evaluate_rules`, hard rule 5): the deadline, document presence and
  expiry (at the deadline and through the bid validity period), tax clearance fiscal year, PAN/VAT,
  licence renewal, turnover, experience, bid security, JV, and per-bid forms. Thresholds and dates
  come from the notice; evidence is a `documents` record with a KB chunk.
- **Layer 2, model** (`assess`): every extracted requirement that no rule covers (licence class,
  key personnel, equipment, liquid assets, ...) gets its own KB retrieval and one
  `ComplianceAssessment` at temperature 0. Code then checks the answer (`ground`): cited chunk ids
  must be among the excerpts shown and the quote must be in the cited chunk, or a pass/fail becomes
  `unclear` (hard rule 8, spec section 17). Code sets the severity: a mandatory requirement is hard.

Any hard failure blocks the tender (`blocked`). Only an explicit override (who, when, why, and which
failures) lets it proceed, and the override stays valid only while the report's hard failures are
all among those accepted. `run_compliance` persists items to `compliance_items` and sets
`checked` / `blocked`, or `failed` if the model or embedding call fails.
"""

import hashlib
import json
import re
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from agents.matching import load_company
from agents.scout import Grounder
from config import Settings, get_settings
from db.models import AgentRunRow, ComplianceItemRow, ComplianceOverrideRow, Document, KBChunk, Tender
from db.search import ChunkHit, retrieve
from nepal.dates import NPT
from nepal.documents import classify_document
from nepal.rules import DOC_RULES, DocumentMeta, evaluate_rules
from pipeline.llm import LLMClient, LLMError
from schemas import (CompanyProfile, ComplianceAssessment, ComplianceItem, ComplianceOverride, ComplianceReport,
                     ComplianceStatus, ComplianceView, IngestStatus, ItemSource, Requirement, RequirementCategory, Severity,
                     Stage, TenderRecord, TenderStatus)

P, F, U = ComplianceStatus.PASS, ComplianceStatus.FAIL, ComplianceStatus.UNCLEAR

# Compliance runs on a pursued tender, or re-runs on one already checked (e.g. after a new document upload).
CHECKABLE = {TenderStatus.MATCHED, TenderStatus.CHECKED, TenderStatus.BLOCKED}

DETERMINISTIC_MODEL = "deterministic"  # agent_runs.model for the rules layer (no LLM call)

SYSTEM_PROMPT = """You check whether a company meets ONE requirement of a public tender in Nepal.

Use ONLY the knowledge-base excerpts given, each marked [chunk N]. Do not use outside knowledge about the company.
- "pass": an excerpt shows the requirement is met.
- "fail": an excerpt shows the requirement is NOT met (e.g. the company's licence class or equipment is below what is asked).
- "unclear": no excerpt says either way, or the excerpts are about something else. When in doubt, answer "unclear".
For pass or fail, list the chunk number(s) in evidence_chunk_ids and copy a short exact sentence or phrase from that
excerpt into evidence_quote (copy it character for character; do not translate or summarise).
Contractor licence classes rank A (highest), B, C, D (lowest); in Nepali क = A, ख = B, ग = C, घ = D ("वर्ग" = class).
"class D or above" is met by A, B, C or D; "class A or B only" is not met by C or D.
Do not judge dates, document expiry, fiscal years, or the bid-security amount: other code checks those.
explanation: one sentence. Reply with JSON only."""

_CHUNK_CHARS = 900
_QUERY_CHARS = 500

# Aspects no rule checks: a requirement mentioning one goes to the model even if a rule covers the rest of it.
_RESIDUAL = re.compile(
    r"\bclass\b|\bcategory\b|वर्ग|श्रेणी|personnel|engineer|staff|manpower|जनशक्ति|इन्जिनियर|equipment|machinery|excavator"
    r"|roller|tipper|mixer|plant|उपकरण|मेसिन|liquid|credit|cash\s*flow|तरलता|कर्जा|\biso\b|certified|methodology|work\s*plan",
    re.I)
_TURNOVER = re.compile(r"turnover|कारोबार", re.I)
_EXPERIENCE = re.compile(r"similar|experience|अनुभव", re.I)
_BID_SECURITY = re.compile(r"bid\s*security|bid\s*bond|बोलपत्र\s*जमानत|धरौटी", re.I)
_RULE_CATEGORIES = {RequirementCategory.ELIGIBILITY, RequirementCategory.FINANCIAL, RequirementCategory.EXPERIENCE}

RetrieveFn = Callable[[str], list[ChunkHit]]


class RetrievalError(LLMError):
    """The embedding call for a KB search failed. Unlike a chat failure, it has no agent_runs row yet."""


# --- which requirements the rules cover ----------------------------------------------------------

def covering_rules(req: Requirement, fired: set[str]) -> list[str]:
    """Rules (among those that produced an item for this tender) that check what `req` asks for.

    Deterministic keyword routing: document types named in the text (`nepal.documents`), plus turnover /
    experience / bid-security wording. A rule that did not fire for this tender (e.g. licence renewal on a goods
    tender) covers nothing.
    """
    text = f"{req.text} {req.source_quote}"
    rules = [DOC_RULES[t] for t in classify_document(text) if t in DOC_RULES]
    if req.category is RequirementCategory.FINANCIAL and _TURNOVER.search(text):
        rules.append("NP-TURNOVER")
    if req.category is RequirementCategory.EXPERIENCE or _EXPERIENCE.search(text):
        rules.append("NP-EXPERIENCE")
    if _BID_SECURITY.search(text):
        rules.append("NP-BID-SECURITY")
    return [r for r in dict.fromkeys(rules) if r in fired]


def needs_model(req: Requirement, covered: list[str]) -> bool:
    """True unless the rules fully cover the requirement (a rule-checkable category with nothing left over)."""
    if not covered or req.category not in _RULE_CATEGORIES:
        return True
    return bool(_RESIDUAL.search(f"{req.text} {req.source_quote}"))


# --- model half ------------------------------------------------------------------------------------

def build_messages(req: Requirement, company: CompanyProfile, chunks: Sequence[ChunkHit],
                   covered: Sequence[str] = ()) -> list[dict[str, str]]:
    note = (f"\nAlready checked by code, do not judge: documents' presence and expiry, fiscal years, turnover and "
            f"contract amounts ({', '.join(covered)}). Judge only the other parts of the requirement.") if covered else ""
    kb = "\n\n".join(f"[chunk {c.chunk_id}] ({c.doc_type.value}, {c.filename})\n{c.content[:_CHUNK_CHARS]}" for c in chunks)
    user = (f"REQUIREMENT ({req.category.value}, {'mandatory' if req.mandatory else 'optional'})\n{req.text}\n"
            f"Notice text: {req.source_quote}{note}\n\nCOMPANY\n{company.name}; sectors: {', '.join(company.sectors) or '-'}\n\n"
            f"KNOWLEDGE BASE EXCERPTS\n{kb or '(none retrieved)'}")
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def assess(client: LLMClient, req: Requirement, company: CompanyProfile, chunks: Sequence[ChunkHit], *,
           covered: Sequence[str] = (), tender_id: int | None = None) -> ComplianceAssessment:
    """One schema-constrained call at temperature 0. Raises LLMError (its agent_runs row is already recorded)."""
    return client.chat(stage=Stage.COMPLIANCE, messages=build_messages(req, company, chunks, covered),
                       schema=ComplianceAssessment, tender_id=tender_id)


def ground(a: ComplianceAssessment, chunks: Sequence[ChunkHit]) -> tuple[ComplianceStatus, list[int], str | None, list[str]]:
    """Check the model's evidence in code: (status, chunk ids, quote, notes). A pass/fail it cannot back is unclear."""
    by_id = {c.chunk_id: c for c in chunks}
    ids = [i for i in dict.fromkeys(a.evidence_chunk_ids) if i in by_id]
    notes = []
    if unknown := [i for i in a.evidence_chunk_ids if i not in by_id]:
        notes.append(f"cited chunk(s) {unknown} were not among the excerpts shown")
    quoted = [i for i in ids if a.evidence_quote and Grounder(by_id[i].content).locate(a.evidence_quote)]
    if a.status is not U and not ids:
        return U, [], None, notes + [f"model said {a.status.value} without a valid evidence chunk, so it is unclear"]
    if a.status is not U and not quoted:
        return U, [], None, notes + [f"model said {a.status.value} but its quote is not in the cited chunk, so it is unclear"]
    return a.status, (quoted or ids), (a.evidence_quote if quoted else None), notes


_UNCLEAR_HINTS = {
    RequirementCategory.PERSONNEL: "CVs and certificates of the named key personnel",
    RequirementCategory.EQUIPMENT: "ownership or hire documents for the listed equipment",
    RequirementCategory.FINANCIAL: "a bank letter or audited statement showing the figure",
    RequirementCategory.TECHNICAL: "a document that shows the technical capability",
}


def model_item(index: int, req: Requirement, chunks: Sequence[ChunkHit], assessment: ComplianceAssessment | None,
               covered: Sequence[str] = ()) -> ComplianceItem:
    """Build the checklist line for one model-judged requirement. Severity is code's: mandatory -> hard."""
    if assessment is None:
        status, ids, quote, notes, why = U, [], None, [], "Not checked: no model was run (offline, rules only)."
    else:
        status, ids, quote, notes = ground(assessment, chunks)
        why = assessment.explanation
    if notes:
        why += " [" + "; ".join(notes) + "]"
    if covered:
        why += f" Document/threshold parts are checked by {', '.join(covered)}."
    docs = {c.chunk_id: c for c in chunks}
    names = ", ".join(dict.fromkeys(docs[i].filename for i in ids))
    if status is P:
        action = None
    elif status is F:
        action = (f"Not met according to {names}: {assessment.explanation} Close the gap before submission, cover it with a "
                  f"JV partner if the notice allows, or skip this tender.")
    else:
        what = _UNCLEAR_HINTS.get(req.category, "a document that shows it")
        action = f"Upload {what} to the knowledge base, or check by hand: \"{req.text}\"."
    return ComplianceItem(
        requirement=req.text, status=status, severity=Severity.HARD if req.mandatory else Severity.SOFT,
        source=ItemSource.MODEL, evidence_chunk_ids=ids,
        evidence_document_ids=list(dict.fromkeys(docs[i].document_id for i in ids)), evidence_quote=quote,
        explanation=why, action_needed=action, requirement_index=index,
    )


# --- the two layers together ---------------------------------------------------------------------

def check_requirements(tender: TenderRecord, company: CompanyProfile, documents: list[DocumentMeta], *,
                       client: LLMClient | None, retrieve_fn: RetrieveFn | None = None, now: datetime | None = None,
                       tender_id: int | None = None) -> ComplianceReport:
    """Layer 1 (rules) then Layer 2 (model, one call per requirement the rules do not cover).

    `client=None` runs the rules only and lists the other requirements as unclear (the offline metric). Raises
    LLMError if a model or embedding call fails; the caller marks the stage failed (hard rule 4).
    """
    rule_items = evaluate_rules(tender, company, documents, now=now)
    fired = {i.rule_id for i in rule_items}
    items = list(rule_items)
    for index, req in enumerate(tender.requirements):
        covered = covering_rules(req, fired)
        if not needs_model(req, covered):
            continue
        if client is None or retrieve_fn is None:
            items.append(model_item(index, req, [], None, covered))
            continue
        chunks = retrieve_fn(req.text[:_QUERY_CHARS])
        assessment = assess(client, req, company, chunks, covered=covered, tender_id=tender_id)
        items.append(model_item(index, req, chunks, assessment, covered))
    return ComplianceReport(items=items)


# --- DB ----------------------------------------------------------------------------------------------

def load_document_meta(session: Session, company_id: int) -> list[DocumentMeta]:
    """`documents` rows -> DocumentMeta. `chunk_id` = the first chunk of a `ready` document (others have none)."""
    first_chunk = (select(KBChunk.document_id, func.min(KBChunk.id).label("chunk_id"))
                   .group_by(KBChunk.document_id).subquery())
    rows = session.execute(
        select(Document, first_chunk.c.chunk_id).outerjoin(first_chunk, first_chunk.c.document_id == Document.id)
        .where(Document.company_id == company_id).order_by(Document.id)
    ).all()
    return [
        DocumentMeta(doc_type=doc.doc_type, document_id=doc.id, filename=doc.filename, expiry=doc.expires_on,
                     fiscal_year_bs=doc.fiscal_year_bs, value_npr=doc.value_npr,
                     chunk_id=chunk_id if doc.ingest_status == IngestStatus.READY.value else None)
        for doc, chunk_id in rows
    ]


def _evidence_text(item: ComplianceItem) -> str | None:
    parts = []
    if item.evidence_chunk_ids:
        parts.append(f"chunks {item.evidence_chunk_ids}")
    if item.evidence_document_ids:
        parts.append(f"documents {item.evidence_document_ids}")
    if item.evidence_ref:
        parts.append(item.evidence_ref)
    if item.evidence_quote:
        parts.append(f'"{item.evidence_quote}"')
    return "; ".join(parts) or None


def to_row(tender_id: int, item: ComplianceItem) -> ComplianceItemRow:
    return ComplianceItemRow(
        tender_id=tender_id, requirement=item.requirement, status=item.status.value, severity=item.severity.value,
        evidence=_evidence_text(item), rule_id=item.rule_id, explanation=item.explanation, source=item.source.value,
        evidence_chunk_ids=item.evidence_chunk_ids, evidence_document_ids=item.evidence_document_ids,
        evidence_ref=item.evidence_ref, evidence_quote=item.evidence_quote, action_needed=item.action_needed,
        requirement_index=item.requirement_index,
    )


def from_row(row: ComplianceItemRow) -> ComplianceItem:
    return ComplianceItem(
        requirement=row.requirement, status=row.status, severity=row.severity, source=row.source, rule_id=row.rule_id,
        evidence_chunk_ids=list(row.evidence_chunk_ids or []), evidence_document_ids=list(row.evidence_document_ids or []),
        evidence_ref=row.evidence_ref, evidence_quote=row.evidence_quote, explanation=row.explanation,
        action_needed=row.action_needed, requirement_index=row.requirement_index,
    )


def load_report(session: Session, tender_id: int) -> ComplianceReport | None:
    rows = session.scalars(select(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender_id)
                           .order_by(ComplianceItemRow.id)).all()
    return ComplianceReport(items=[from_row(r) for r in rows]) if rows else None


def latest_override(session: Session, tender_id: int) -> ComplianceOverrideRow | None:
    return session.scalars(select(ComplianceOverrideRow).where(ComplianceOverrideRow.tender_id == tender_id)
                           .order_by(ComplianceOverrideRow.id.desc()).limit(1)).first()


def override_covers(override: ComplianceOverrideRow | None, report: ComplianceReport) -> bool:
    """An override holds while every current hard failure is one the person accepted."""
    return override is not None and {i.key for i in report.hard_failures} <= set(override.hard_failures)


def compliance_view(session: Session, tender_id: int) -> ComplianceView | None:
    report = load_report(session, tender_id)
    if report is None:
        return None
    row = latest_override(session, tender_id)
    override = ComplianceOverride(
        id=row.id, overridden_by=row.overridden_by, reason=row.reason, overridden_at=row.created_at,
        hard_failures=list(row.hard_failures), active=report.is_blocked and override_covers(row, report),
    ) if row else None
    return ComplianceView(items=report.items, override=override)


def _record_code_run(session: Session, tender: Tender, payload: dict[str, Any], started: float, *,
                     items: list[ComplianceItem] | None = None, error: str | None = None) -> None:
    """agent_runs row for the rules layer or a failed KB retrieval (hard rule 9). Model calls record their own rows."""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    session.add(AgentRunRow(
        tender_id=tender.id, stage=Stage.COMPLIANCE.value, model=DETERMINISTIC_MODEL, input_hash=digest,
        output_json={"items": [i.model_dump(mode="json") for i in items]} if items is not None else None,
        latency_ms=int((time.perf_counter() - started) * 1000), ok=error is None, attempts=1, error=error,
    ))


def run_compliance(session: Session, client: LLMClient, tender: Tender, *, settings: Settings | None = None,
                   now: datetime | None = None) -> ComplianceReport | None:
    """Check one pursued tender: replace its compliance_items, set checked/blocked (failed on LLMError)."""
    settings = settings or get_settings()
    if TenderStatus(tender.status) not in CHECKABLE or tender.record_json is None:
        raise ValueError(f"tender {tender.id} is {tender.status}; Compliance runs on matched/checked/blocked tenders")
    loaded = load_company(session)
    if loaded is None:
        raise ValueError("no company profile; POST /company first")
    company_row, company = loaded
    record = TenderRecord.model_validate(tender.record_json)
    documents = load_document_meta(session, company_row.id)
    now = now or datetime.now(NPT)
    started = time.perf_counter()
    payload = {"tender": tender.record_json, "company": company_row.profile_json, "now": now, "stage": "compliance",
               "documents": [d.model_dump(mode="json") for d in documents]}

    def retrieve_fn(query: str) -> list[ChunkHit]:
        try:
            return retrieve(session, client, query, settings.compliance_top_k, company_id=company_row.id)
        except LLMError as exc:
            raise RetrievalError(str(exc)) from exc

    try:
        report = check_requirements(record, company, documents, client=client, retrieve_fn=retrieve_fn, now=now,
                                    tender_id=tender.id)
    except LLMError as exc:
        # A chat failure is already in agent_runs (client); an embedding failure is not, so record it here.
        if isinstance(exc, RetrievalError):
            _record_code_run(session, tender, payload, started, error=f"KB retrieval failed: {exc}")
        session.execute(delete(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id))
        tender.status = TenderStatus.FAILED.value
        tender.updated_at = func.now()
        session.commit()
        return None

    _record_code_run(session, tender, payload, started, items=[i for i in report.items if i.source is ItemSource.RULE])
    session.execute(delete(ComplianceItemRow).where(ComplianceItemRow.tender_id == tender.id))
    session.add_all(to_row(tender.id, item) for item in report.items)
    blocked = report.is_blocked and not override_covers(latest_override(session, tender.id), report)
    tender.status = (TenderStatus.BLOCKED if blocked else TenderStatus.CHECKED).value
    tender.updated_at = func.now()
    session.commit()
    return report


def override_block(session: Session, tender: Tender, *, overridden_by: str, reason: str) -> ComplianceOverrideRow:
    """A named person accepts the current hard failures: store who/when/why/which, and set the tender `checked`."""
    if tender.status != TenderStatus.BLOCKED.value:
        raise ValueError(f"tender {tender.id} is {tender.status}; only a blocked tender can be overridden")
    report = load_report(session, tender.id)
    if report is None or not report.is_blocked:
        raise ValueError(f"tender {tender.id} has no hard compliance failure to override")
    row = ComplianceOverrideRow(tender_id=tender.id, overridden_by=overridden_by, reason=reason,
                                hard_failures=[i.key for i in report.hard_failures])
    session.add(row)
    tender.status = TenderStatus.CHECKED.value
    tender.updated_at = func.now()
    session.commit()
    return row


def proposal_allowed(session: Session, tender: Tender) -> tuple[bool, str]:
    """The Proposal gate: compliance has run, and there is no hard failure unless an active override covers it."""
    if tender.status == TenderStatus.BLOCKED.value:
        return False, "blocked by hard compliance failures; resolve them or override (POST /tenders/{id}/compliance/override)"
    view = compliance_view(session, tender.id)
    if view is None or TenderStatus(tender.status) not in {TenderStatus.CHECKED, TenderStatus.DRAFTED, TenderStatus.REVIEWED}:
        return False, f"tender is {tender.status}; run POST /tenders/{{id}}/analyze until it is checked"
    if not view.proposal_allowed:
        return False, "hard compliance failures are not covered by an override"
    return True, "ok"
