"""Proposal approval and package endpoints (spec section 10.2).

Not implemented yet: see routers/tenders.py docstring.
"""

from fastapi import APIRouter, HTTPException, status

from schemas import Proposal

router = APIRouter(prefix="/proposals", tags=["proposals"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."
_501 = {status.HTTP_501_NOT_IMPLEMENTED: {"description": "Not implemented yet"}}


@router.post("/{proposal_id}/approve", responses=_501)
def approve_proposal(proposal_id: int) -> Proposal:
    """Human approval; sets status. This is the mandatory human gate (CLAUDE.md)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{proposal_id}/package", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def download_package(proposal_id: int):
    """Download submission package (export/package.py)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
