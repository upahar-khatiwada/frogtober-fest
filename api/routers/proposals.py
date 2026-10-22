"""Proposal endpoints (spec section 10.2).

GET /proposals/{id} (one stored version; drafting + review is POST /tenders/{id}/proposal), POST /proposals/{id}/open
(a person opened it; the UI calls it when it shows the version), POST /proposals/{id}/approve (the human gate:
reviewed, verdict not fail, opened after the review; writes an audit row) and GET /proposals/{id}/package (the ZIP of
an approved version; nothing is ever submitted, hard rule 6). The proposal page also uses
POST /proposals/{id}/sections/{key}/edit (a person's edit, saved as a new version), POST /proposals/{id}/review
(re-review the latest version, without the automatic revision), GET /proposals/{id}/checklist and
GET /proposals/{id}/export/{pdf|docx} (the package's bid document on its own).
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, sessionmaker

from agents.proposal import edit_section, latest_proposal, proposal_from_row
from agents.review import approve_proposal, mark_opened
from config import Settings
from db.models import ProposalRow, Tender
from deps import get_llm_client, get_now, get_session, get_sessionmaker, get_settings
from export.package import PackageNotReady, build, checklist, render
from pipeline import orchestrator
from pipeline.llm import LLMClient
from routers.runs import run_view
from schemas import (ApprovalRequest, ChecklistItem, PipelineRunView, Proposal, SectionEditRequest, Stage,
                     TenderStatus)

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


_MEDIA = {"pdf": "application/pdf",
          "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@router.get("/{proposal_id}/export/{fmt}",
            responses=_404 | {status.HTTP_409_CONFLICT: {"description": "The version is not approved"},
                              status.HTTP_200_OK: {"content": {m: {} for m in _MEDIA.values()},
                                                   "description": "The bid package document"}},
            response_class=Response)
def download_document(proposal_id: int, fmt: Literal["pdf", "docx"], session: Annotated[Session, Depends(get_session)],
                      now: Annotated[datetime, Depends(get_now)]) -> Response:
    """The approved version's bid package as one PDF or DOCX (the same file the ZIP holds)."""
    try:
        filename, content = render(session, _row(session, proposal_id), fmt, now=now)
    except PackageNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return Response(content=content, media_type=_MEDIA[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{proposal_id}/checklist",
            responses=_404 | {status.HTTP_409_CONFLICT: {"description": "The tender record or company is missing"}})
def get_checklist(proposal_id: int, session: Annotated[Session, Depends(get_session)],
                  now: Annotated[datetime, Depends(get_now)]) -> list[ChecklistItem]:
    """The attachment checklist for this version: every document the notice lists (+ statutory ones), present /
    expiring / missing against the knowledge base, with dates in BS and AD. Readable before approval."""
    try:
        return checklist(session, _row(session, proposal_id), now=now)
    except PackageNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{proposal_id}/sections/{section_key}/edit", status_code=status.HTTP_201_CREATED,
             responses=_404 | {status.HTTP_409_CONFLICT: {
                 "description": "Not the latest version, tender approved or not drafted/reviewed, a run is active, "
                                "or the text is unchanged"}})
def edit_proposal_section(proposal_id: int, section_key: str, body: SectionEditRequest,
                          session: Annotated[Session, Depends(get_session)],
                          now: Annotated[datetime, Depends(get_now)]) -> Proposal:
    """A person's edit of one section, saved as a NEW version (the edited version is kept unchanged).

    The new version is a draft: it has no review, so it cannot be approved until POST /proposals/{id}/review has run
    on it. Citations stay as drafted; flags whose markers were edited out are dropped. Writes an audit row.
    """
    row = _row(session, proposal_id)
    try:
        new_row = edit_section(session, row, section_key, body=body.body, edited_by=body.edited_by, note=body.note,
                               now=now)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return proposal_from_row(new_row)


@router.post("/{proposal_id}/review", status_code=status.HTTP_202_ACCEPTED,
             responses=_404 | {status.HTTP_409_CONFLICT: {
                 "description": "Not the latest version, already reviewed or approved, or a run is active"}})
def review_version(
    proposal_id: int,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
    client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> PipelineRunView:
    """Run Review on the latest version (e.g. after a person's edit), in the background. Poll GET /runs/{id}.

    Unlike POST /tenders/{id}/proposal there is no automatic revision: the model never rewrites a person's text.
    """
    row = _row(session, proposal_id)
    tender = session.get(Tender, row.tender_id)
    latest = latest_proposal(session, row.tender_id)
    if latest is None or latest.id != row.id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"version {row.version} is not the latest; review the latest")
    if row.review_json is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"version {row.version} is already reviewed")
    if tender.status not in (TenderStatus.DRAFTED.value, TenderStatus.REVIEWED.value, TenderStatus.FAILED.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"tender {tender.id} is {tender.status}")
    runners = orchestrator.default_runners(settings, now, auto_revise=False)
    try:
        run = orchestrator.start_run(session, tender, target=TenderStatus.REVIEWED, from_stage=Stage.REVIEW,
                                     runners=runners)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    background.add_task(orchestrator.execute_run, factory, client, run.id, settings=settings, now=now, runners=runners)
    return run_view(run, tender.title)
