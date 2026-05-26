from fastapi import APIRouter, Depends, HTTPException, status

from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.models import (
    GraphAnalysisResponse,
)


router = APIRouter(tags=["graph"])


def require_project(project_id: str, data_store: WritingDataStore) -> None:
    if not data_store.project_exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )


@router.get(
    "/projects/{project_id}/graph/analysis",
    response_model=GraphAnalysisResponse,
)
def analyze_project_graph(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> GraphAnalysisResponse:
    require_project(project_id, data_store)
    snapshot = build_project_snapshot(project_id, data_store)
    return cognition.graph_module.analyze(snapshot)
