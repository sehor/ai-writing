"""Pure HTTP layer for write-back proposal routes."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError

from app.analysis.http import apply_analysis_headers
from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.llm import ModelGatewayError
from app.models import (
    HermesRevisionProcessResponse,
    ProviderGenerationRequest,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatusUpdate,
)
from app.review.service import (
    WritebackPreValidationError,
    unprocessable_from,
)
from app.services.writeback_service import (
    RevisionNotFoundError,
    SceneForRevisionNotFoundError,
    WritebackService,
    get_writeback_service,
)


router = APIRouter(tags=["writeback"])


@router.get(
    "/projects/{project_id}/writeback/proposals",
    response_model=list[WritebackProposal],
)
def list_writeback_proposals(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[WritebackProposal]:
    require_project(project_id, data_store)
    return data_store.list_writeback_proposals(project_id)


@router.post(
    "/projects/{project_id}/writeback/proposals",
    response_model=WritebackProposal,
    status_code=status.HTTP_201_CREATED,
)
def create_writeback_proposal(
    project_id: str,
    proposal: WritebackProposalCreate,
    service: WritebackService = Depends(get_writeback_service),
) -> WritebackProposal:
    require_project(project_id, service.data_store)
    try:
        return service.create_proposal(project_id, proposal)
    except WritebackPreValidationError as exc:
        raise unprocessable_from(exc) from exc


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}",
    response_model=list[WritebackProposal],
    status_code=status.HTTP_201_CREATED,
)
def create_writeback_proposals_from_revision(
    project_id: str,
    revision_id: str,
    response: Response,
    force: bool = False,
    service: WritebackService = Depends(get_writeback_service),
) -> list[WritebackProposal]:
    require_project(project_id, service.data_store)
    try:
        outcome = service.generate_from_revision(project_id, revision_id, force=force)
    except RevisionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        ) from exc
    apply_analysis_headers(response, outcome)
    return outcome.proposals


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/hermes",
    response_model=HermesRevisionProcessResponse,
    status_code=status.HTTP_201_CREATED,
)
def process_revision_with_hermes(
    project_id: str,
    revision_id: str,
    force: bool = False,
    service: WritebackService = Depends(get_writeback_service),
) -> HermesRevisionProcessResponse:
    require_project(project_id, service.data_store)
    try:
        return service.process_with_hermes(project_id, revision_id, force=force)
    except RevisionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        ) from exc
    except SceneForRevisionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found for manuscript revision.",
        ) from exc


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/provider",
    response_model=list[WritebackProposal],
    status_code=status.HTTP_201_CREATED,
)
def create_provider_writeback_proposals_from_revision(
    project_id: str,
    revision_id: str,
    response: Response,
    request: ProviderGenerationRequest | None = None,
    force: bool = False,
    service: WritebackService = Depends(get_writeback_service),
) -> list[WritebackProposal]:
    require_project(project_id, service.data_store)
    try:
        outcome = service.generate_provider_from_revision(
            project_id,
            revision_id,
            force=force,
            options=request or ProviderGenerationRequest(),
        )
    except RevisionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        ) from exc
    except WritebackPreValidationError as exc:
        raise unprocessable_from(exc) from exc
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_501_NOT_IMPLEMENTED
                if exc.is_configuration_error
                else status.HTTP_502_BAD_GATEWAY
            ),
            detail=exc.safe_message,
        ) from exc
    apply_analysis_headers(response, outcome)
    return outcome.proposals


@router.put(
    "/projects/{project_id}/writeback/proposals/{proposal_id}/status",
    response_model=WritebackProposal,
)
def update_writeback_proposal_status(
    project_id: str,
    proposal_id: str,
    update: WritebackProposalStatusUpdate,
    service: WritebackService = Depends(get_writeback_service),
) -> WritebackProposal:
    require_project(project_id, service.data_store)
    try:
        proposal = service.update_status(project_id, proposal_id, update.status)
    except ValidationError as exc:
        # A stored proposal whose payload no longer matches its target shape.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Write-back payload does not match the target record shape.",
        ) from exc
    except ValueError as exc:
        # Illegal review transitions and version conflicts share 409.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Accepted write-back would duplicate an existing record.",
        ) from exc
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Write-back proposal not found.",
        )
    return proposal
