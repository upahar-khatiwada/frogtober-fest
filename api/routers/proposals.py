"""Proposal endpoints (spec section 10.2).

GET /proposals/{id} (one stored version; drafting + review is POST /tenders/{id}/proposal), POST /proposals/{id}/open
(a person opened it; the UI calls it when it shows the version), POST /proposals/{id}/approve (the human gate:
reviewed, verdict not fail, opened after the review; writes an audit row) and GET /proposals/{id}/package (the ZIP of
an approved version; nothing is ever submitted, hard rule 6).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from agents.proposal import proposal_from_row
from agents.review import approve_proposal, mark_opened
from db.models import ProposalRow
from deps import get_now, get_session
from export.package import PackageNotReady, build
from schemas import ApprovalRequest, Proposal

router = APIRouter(prefix="/proposals", tags=["proposals"])

_404 = {status.HTTP_404_NOT_FOUND: {"description": "No such proposal"}}


def _row(session: Session, proposal_id: int) -> ProposalRow:
    row = session.get(ProposalRow, proposal_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No proposal {proposal_id}")
    return row


@router.get("/{proposal_id}", responses=_404)
def get_proposal(proposal_id: int, session: Annotated[Session, Depends(get_session)]) -> Proposal:
    """One proposal version: sections with their cited chunk ids, grounding, flags and its review."""
    return proposal_from_row(_row(session, proposal_id))


@router.post("/{proposal_id}/open", responses=_404)
def open_proposal(proposal_id: int, session: Annotated[Session, Depends(get_session)],
                  now: Annotated[datetime, Depends(get_now)]) -> Proposal:
    """Record that a person opened this version. Approval needs an open after the version's review."""
    return proposal_from_row(mark_opened(session, _row(session, proposal_id), now))


@router.post("/{proposal_id}/approve",
             responses=_404 | {status.HTTP_409_CONFLICT: {
                 "description": "Not reviewed, verdict fail, not opened since its review, tender not reviewed, a run "
                                "is active, or already approved"}})
def approve(proposal_id: int, body: ApprovalRequest, session: Annotated[Session, Depends(get_session)],
            now: Annotated[datetime, Depends(get_now)]) -> Proposal:
    """Human approval: sets the version `approved` (with who, when, note) and the tender `approved`.

    This is the mandatory human gate (CLAUDE.md): refused while the review verdict is `fail` or the reviewed version
    has not been opened. Every approval writes an agent_runs audit row (stage review, model "human").
    """
    row = _row(session, proposal_id)
    try:
        approve_proposal(session, row, approved_by=body.approved_by, note=body.note, now=now)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return proposal_from_row(row)


@router.get("/{proposal_id}/package",
            responses=_404 | {status.HTTP_409_CONFLICT: {"description": "The version is not approved"},
                              status.HTTP_200_OK: {"content": {"application/zip": {}},
                                                   "description": "The submission package (ZIP)"}},
            response_class=Response)
def download_package(proposal_id: int, session: Annotated[Session, Depends(get_session)],
                     now: Annotated[datetime, Depends(get_now)]) -> Response:
    """The submission package of an approved version: bid package PDF + DOCX, attachment checklist (CSV), audit
    summary (JSON) and the KB documents the checklist marks present. Built on demand; never sent anywhere."""
    row = _row(session, proposal_id)
    try:
        built = build(session, row, now=now)
    except PackageNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return Response(content=built.content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{built.filename}"'})
