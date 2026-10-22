"""Proposal endpoints (spec section 10.2).

Implemented: GET /proposals/{id} (one stored version; drafting is POST /tenders/{id}/proposal).
Not implemented yet: approval and the package (see PROGRESS.md Next prompt).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from agents.proposal import proposal_from_row
from db.models import ProposalRow
from deps import get_session
from schemas import Proposal

router = APIRouter(prefix="/proposals", tags=["proposals"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."
_501 = {status.HTTP_501_NOT_IMPLEMENTED: {"description": "Not implemented yet"}}


@router.get("/{proposal_id}", responses={status.HTTP_404_NOT_FOUND: {"description": "No such proposal"}})
def get_proposal(proposal_id: int, session: Annotated[Session, Depends(get_session)]) -> Proposal:
    """One proposal version: sections with their cited chunk ids, grounding and flags."""
    row = session.get(ProposalRow, proposal_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No proposal {proposal_id}")
    return proposal_from_row(row)


@router.post("/{proposal_id}/approve", responses=_501)
def approve_proposal(proposal_id: int) -> Proposal:
    """Human approval; sets status. This is the mandatory human gate (CLAUDE.md)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{proposal_id}/package", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def download_package(proposal_id: int):
    """Download submission package (export/package.py)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
