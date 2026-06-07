import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.models import CanonEntity, CanonEntityCreate, CanonEntityUpdate


router = APIRouter(tags=["canon"])


@router.get("/projects/{project_id}/canon/entities", response_model=list[CanonEntity])
def list_canon_entities(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[CanonEntity]:
    require_project(project_id, data_store)
    return data_store.list_canon_entities(project_id)


@router.post(
    "/projects/{project_id}/canon/entities",
    response_model=CanonEntity,
    status_code=status.HTTP_201_CREATED,
)
def create_canon_entity(
    project_id: str,
    entity: CanonEntityCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> CanonEntity:
    require_project(project_id, data_store)
    try:
        return data_store.create_canon_entity(project_id, entity)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Canon entity already exists for this project and type.",
        ) from exc


@router.put(
    "/projects/{project_id}/canon/entities/{entity_id}",
    response_model=CanonEntity,
)
def update_canon_entity(
    project_id: str,
    entity_id: str,
    entity: CanonEntityUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> CanonEntity:
    require_project(project_id, data_store)
    try:
        updated = data_store.update_canon_entity(project_id, entity_id, entity)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Canon entity already exists for this project and type.",
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canon entity not found.",
        )
    return updated


@router.delete(
    "/projects/{project_id}/canon/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_canon_entity(
    project_id: str,
    entity_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> Response:
    require_project(project_id, data_store)
    deleted = data_store.delete_canon_entity(project_id, entity_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canon entity not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
