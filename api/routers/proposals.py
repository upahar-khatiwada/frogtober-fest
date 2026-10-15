"""Proposal approval and package endpoints (spec section 10.2).

Not implemented yet: see routers/tenders.py docstring.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/proposals", tags=["proposals"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."


@router.post("/{proposal_id}/approve", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def approve_proposal(proposal_id: int):
    """Human approval; sets status. This is the mandatory human gate (CLAUDE.md)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{proposal_id}/package", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def download_package(proposal_id: int):
    """Download submission package (export/package.py)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)