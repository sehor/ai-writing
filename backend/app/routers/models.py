"""Model selection and safe generation-run inspection endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_project
from app.models import GenerationRun, ModelProfileView
from app.services.model_service import ModelService, get_model_service


router = APIRouter(tags=["models"])


@router.get("/model-profiles", response_model=list[ModelProfileView])
def list_model_profiles(
    service: ModelService = Depends(get_model_service),
) -> list[ModelProfileView]:
    return service.list_profiles()


@router.get(
    "/projects/{project_id}/generation-runs",
    response_model=list[GenerationRun],
)
def list_generation_runs(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    service: ModelService = Depends(get_model_service),
) -> list[GenerationRun]:
    require_project(project_id, service.data_store)
    return service.list_runs(project_id, limit)


@router.get(
    "/projects/{project_id}/generation-runs/{run_id}",
    response_model=GenerationRun,
)
def get_generation_run(
    project_id: str,
    run_id: str,
    service: ModelService = Depends(get_model_service),
) -> GenerationRun:
    require_project(project_id, service.data_store)
    run = service.get_run(project_id, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run not found.",
        )
    return run


__all__ = ["router"]
