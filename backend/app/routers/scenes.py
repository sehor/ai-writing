import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.models import (
    ChapterCompileResponse,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
)
from app.services.compile_service import CompileService


router = APIRouter(tags=["scenes"])


@router.get(
    "/projects/{project_id}/scene-contracts",
    response_model=list[SceneContract],
)
def list_scene_contracts(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[SceneContract]:
    require_project(project_id, data_store)
    return data_store.list_scene_contracts(project_id)


@router.post(
    "/projects/{project_id}/scene-contracts",
    response_model=SceneContract,
    status_code=status.HTTP_201_CREATED,
)
def create_scene_contract(
    project_id: str,
    scene: SceneContractCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> SceneContract:
    require_project(project_id, data_store)
    try:
        return data_store.create_scene_contract(project_id, scene)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scene sequence already exists for this project.",
        ) from exc


@router.put(
    "/projects/{project_id}/scene-contracts/{scene_id}",
    response_model=SceneContract,
)
def update_scene_contract(
    project_id: str,
    scene_id: str,
    scene: SceneContractUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> SceneContract:
    require_project(project_id, data_store)
    try:
        updated = data_store.update_scene_contract(project_id, scene_id, scene)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scene sequence already exists for this project.",
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )
    return updated


@router.delete(
    "/projects/{project_id}/scene-contracts/{scene_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scene_contract(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> Response:
    require_project(project_id, data_store)
    deleted = data_store.delete_scene_contract(project_id, scene_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/scene-contracts/{scene_id}/compile",
    response_model=ChapterCompileResponse,
)
def compile_scene_contract(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    service: CompileService = Depends(),
) -> ChapterCompileResponse:
    require_project(project_id, data_store)
    return service.compile_scene_contract(project_id, scene_id)
