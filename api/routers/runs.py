"""Pipeline run log endpoints (spec section 10.2).

Not implemented yet: see routers/tenders.py docstring. Backed by the
agent_runs table (spec section 11) once DB models exist.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/runs", tags=["runs"])

_NOT_IMPLEMENTED = "Not implemented yet - see PROGRESS.md Next prompt."


@router.get("/{run_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_run(run_id: int):
    """Run status for polling (web/ polls this every 2s per spec section 9.2)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)