"""Pure HTTP layer for reference / copilot suggestion routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.llm import ModelGatewayError
from app.models import (
    ReferenceGenerationRequest,
    ReferenceSuggestion,
    ReferenceSuggestionStatusUpdate,
)
from app.services.reference_service import ReferenceService, get_reference_service


router = APIRouter(tags=["references"])


@router.get(
    "/projects/{project_id}/references/suggestions",
    response_model=list[ReferenceSuggestion],
)
def list_reference_suggestions(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[ReferenceSuggestion]:
    require_project(project_id, data_store)
    return data_store.list_reference_suggestions(project_id)


@router.post(
    "/projects/{project_id}/references/suggestions/generate",
    response_model=ReferenceSuggestion,
    status_code=status.HTTP_201_CREATED,
)
def generate_reference_suggestion(
    project_id: str,
    request: ReferenceGenerationRequest,
    service: ReferenceService = Depends(get_reference_service),
) -> ReferenceSuggestion:
    require_project(project_id, service.data_store)
    return service.generate_local(project_id, request)


@router.post(
    "/projects/{project_id}/references/suggestions/generate/provider",
    response_model=ReferenceSuggestion,
    status_code=status.HTTP_201_CREATED,
)
def generate_provider_reference_suggestion(
    project_id: str,
    request: ReferenceGenerationRequest,
    service: ReferenceService = Depends(get_reference_service),
) -> ReferenceSuggestion:
    require_project(project_id, service.data_store)
    try:
        return service.generate_provider(project_id, request)
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_501_NOT_IMPLEMENTED
                if exc.is_configuration_error
                else status.HTTP_502_BAD_GATEWAY
            ),
            detail=exc.safe_message,
        ) from exc


@router.put(
    "/projects/{project_id}/references/suggestions/{suggestion_id}/status",
    response_model=ReferenceSuggestion,
)
def update_reference_suggestion_status(
    project_id: str,
    suggestion_id: str,
    update: ReferenceSuggestionStatusUpdate,
    service: ReferenceService = Depends(get_reference_service),
) -> ReferenceSuggestion:
    require_project(project_id, service.data_store)
    try:
        suggestion = service.update_status(project_id, suggestion_id, update.status)
    except ValueError as exc:
        # Illegal review transition: already reviewed, cannot change again.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference suggestion not found.",
        )
    return suggestion
