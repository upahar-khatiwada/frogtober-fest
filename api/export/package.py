"""The submission-ready package (spec sections 5.1, 6): one ZIP built on demand for an approved proposal version.

    01_<stem>.pdf               bid package (fixed layout, embedded Noto fonts; Devanagari shaped)
    01_<stem>.docx              the same, editable
    02_attachment_checklist.csv every required document: present / expiring / missing, dates in BS and AD
    03_audit_summary.json       tender, proposal, review, approval, compliance, checklist, every agent_runs row, file hashes
    attachments/<id>_<file>     the KB originals the checklist marks present or expiring

Nothing is sent anywhere (hard rule 6): the person submits the package themselves. Built from stored rows only (no
model call), so the same approved version and clock give the same contents.
"""

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.compliance import compliance_view, load_document_meta
from agents.matching import load_company
from agents.proposal import proposal_from_row
from db.models import AgentRunRow, Document, ProposalRow, Tender
from export.content import BidPackage, bs_ad, build_package
from export.docx import render_docx
from export.pdf import render_pdf
from nepal.dates import NPT, ad_to_bs
from schemas import ChecklistStatus, ProposalStatus, TenderRecord

CHECKLIST_FIELDS = ("document", "doc_type", "mandatory", "fiscal_year_bs", "status", "files", "expires_on_ad",
                    "expires_on_bs", "rule_id", "compliance_status", "note")


class PackageNotReady(ValueError):
    """The proposal cannot be packaged (not approved, or its tender/company is gone)."""


@dataclass
class BuiltPackage:
    filename: str
    content: bytes
    package: BidPackage
    files: list[dict[str, Any]]


def checklist_csv(package: BidPackage) -> bytes:
    """UTF-8 with BOM, so Excel opens the Devanagari correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CHECKLIST_FIELDS)
    for row in package.checklist:
        writer.writerow([row.document, row.doc_type.value, row.mandatory, row.fiscal_year_bs or "", row.status.value,
                         "; ".join(row.files), row.expires_on.isoformat() if row.expires_on else "",
                         row.expires_on_bs or "", row.rule_id or "",
                         row.compliance_status.value if row.compliance_status else "", row.note])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _agent_runs(session: Session, tender_id: int) -> list[dict[str, Any]]:
    rows = session.scalars(select(AgentRunRow).where(AgentRunRow.tender_id == tender_id).order_by(AgentRunRow.id)).all()
    return [{"id": r.id, "stage": r.stage, "model": r.model, "input_hash": r.input_hash, "latency_ms": r.latency_ms,
             "ok": r.ok, "attempts": r.attempts, "cached": r.cached, "error": r.error,
             "pipeline_run_id": r.pipeline_run_id, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


def build(session: Session, row: ProposalRow, *, now: datetime) -> BuiltPackage:
    """The ZIP for one approved proposal version. Raises PackageNotReady."""
    if row.status != ProposalStatus.APPROVED.value:
        raise PackageNotReady(f"proposal {row.id} (version {row.version}) is {row.status}; only an approved version "
                              f"is packaged (POST /proposals/{row.id}/approve)")
    tender = session.get(Tender, row.tender_id)
    loaded = load_company(session)
    if tender is None or tender.record_json is None or loaded is None:
        raise PackageNotReady(f"proposal {row.id}: its tender record or the company profile is missing")
    company_row, company = loaded
    record = TenderRecord.model_validate(tender.record_json)
    proposal = proposal_from_row(row)
    compliance = compliance_view(session, tender.id)
    documents = load_document_meta(session, company_row.id)
    package = build_package(record=record, company=company, proposal=proposal, compliance=compliance,
                            documents=documents, now=now, tender_id=tender.id)

    files: dict[str, bytes] = {
        f"01_{package.file_stem}.pdf": render_pdf(package, generated=now),
        f"01_{package.file_stem}.docx": render_docx(package, generated=now),
        "02_attachment_checklist.csv": checklist_csv(package),
    }
    attach = sorted({i for item in package.checklist if item.status is not ChecklistStatus.MISSING for i in item.document_ids})
    for doc in session.scalars(select(Document).where(Document.id.in_(attach)).order_by(Document.id)) if attach else []:
        files[f"attachments/{doc.id}_{doc.filename}"] = doc.content
    listing = [{"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()]

    deadline = record.deadline_ad
    audit = {
        "generated_at": now.isoformat(), "generated_at_bs": ad_to_bs(now.astimezone(NPT).date()).iso(),
        "submitted": False,
        "notice": "Prepared with Tenderly. Tenderly never submits bids, logs in to portals or uploads anything; the "
                  "person submits this package through the procuring entity's channel.",
        "tender": {"id": tender.id, "title": record.title, "reference_no": record.reference_no, "buyer": record.buyer,
                   "source_url": tender.source_url, "status": tender.status,
                   "deadline_ad": deadline.isoformat() if deadline else None,
                   "deadline_bs": bs_ad(deadline.astimezone(NPT).date(), package.language) if deadline else None},
        "proposal": {"id": proposal.id, "version": proposal.version, "language": proposal.language.value,
                     "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
                     "citation_rate": proposal.citation_rate,
                     "sections": [{"key": s.key, "title": s.title, "cited_chunk_ids": s.cited_chunk_ids,
                                   "grounded": s.grounded, "flags": [f.kind.value for f in s.flags]}
                                  for s in proposal.sections]},
        "review": proposal.review.model_dump(mode="json") if proposal.review else None,
        "approval": {"approved_by": proposal.approved_by, "note": proposal.approval_note,
                     "approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
                     "opened_at": proposal.opened_at.isoformat() if proposal.opened_at else None,
                     "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None},
        "compliance": compliance.model_dump(mode="json") if compliance else None,
        "checklist": [item.model_dump(mode="json") for item in package.checklist],
        "agent_runs": _agent_runs(session, tender.id),
        "files": listing,
    }
    files["03_audit_summary.json"] = json.dumps(audit, ensure_ascii=False, indent=2).encode("utf-8")

    buffer = io.BytesIO()
    stamp = now.astimezone(NPT).timetuple()[:6]
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return BuiltPackage(filename=f"tenderly_{package.file_stem}_package.zip", content=buffer.getvalue(),
                        package=package, files=listing)
