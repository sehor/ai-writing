from fastapi import APIRouter, Depends, HTTPException, status

from app.agents import DeepSeekSettings, WorkflowNotConfiguredError
from app.agents.reference_workflow import (
    build_local_reference_suggestion,
    build_provider_reference_suggestion,
    build_reference_context,
    scope_for_request,
)
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.models import (
    ReferenceGenerationRequest,
    ReferenceSuggestion,
    ReferenceSuggestionStatusUpdate,
)


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
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> ReferenceSuggestion:
    require_project(project_id, data_store)
    snapshot = build_project_snapshot(project_id, data_store)
    cognition_context = cognition.prepare_context(snapshot, scope_for_request(request))
    context = build_reference_context(snapshot, request, cognition_context)
    suggestion = build_local_reference_suggestion(
        request,
        context,
        snapshot,
        cognition_context,
    )
    return data_store.create_reference_suggestion(project_id, suggestion)


@router.post(
    "/projects/{project_id}/references/suggestions/generate/provider",
    response_model=ReferenceSuggestion,
    status_code=status.HTTP_201_CREATED,
)
def generate_provider_reference_suggestion(
    project_id: str,
    request: ReferenceGenerationRequest,
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> ReferenceSuggestion:
    require_project(project_id, data_store)
    settings = DeepSeekSettings.from_env()
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="DeepSeek provider is not configured.",
        )
    snapshot = build_project_snapshot(project_id, data_store)
    cognition_context = cognition.prepare_context(snapshot, scope_for_request(request))
    context = build_reference_context(snapshot, request, cognition_context)
    try:
        suggestion = build_provider_reference_suggestion(
            settings,
            request,
            context,
            snapshot,
            cognition_context,
        )
    except WorkflowNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider reference generation failed: {exc}",
        ) from exc
    return data_store.create_reference_suggestion(project_id, suggestion)


@router.put(
    "/projects/{project_id}/references/suggestions/{suggestion_id}/status",
    response_model=ReferenceSuggestion,
)
def update_reference_suggestion_status(
    project_id: str,
    suggestion_id: str,
    update: ReferenceSuggestionStatusUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> ReferenceSuggestion:
    require_project(project_id, data_store)
    suggestion = data_store.update_reference_suggestion_status(
        project_id,
        suggestion_id,
        update.status,
    )
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference suggestion not found.",
        )
    return suggestion
