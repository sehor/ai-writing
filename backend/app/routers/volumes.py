from fastapi import APIRouter, Depends, Response
from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.errors import ResourceNotFoundError
from app.domain_models.volume import (
    ManuscriptVolume,
    ManuscriptVolumeCreate,
    ChapterVolumeAssignment,
    ChapterVolumeMembership,
)

router = APIRouter(tags=["manuscript"])


@router.get("/projects/{project_id}/manuscript/volumes", response_model=list[ManuscriptVolume])
def list_volumes(
    project_id: str, store: WritingDataStore = Depends(get_data_store)
) -> list[ManuscriptVolume]:
    require_project(project_id, store)
    return store.list_manuscript_volumes(project_id)


@router.post(
    "/projects/{project_id}/manuscript/volumes", response_model=ManuscriptVolume, status_code=201
)
def create_volume(
    project_id: str,
    create: ManuscriptVolumeCreate,
    store: WritingDataStore = Depends(get_data_store),
) -> ManuscriptVolume:
    require_project(project_id, store)
    return store.create_manuscript_volume(project_id, create)


@router.put(
    "/projects/{project_id}/manuscript/volumes/{volume_id}", response_model=ManuscriptVolume
)
def update_volume(
    project_id: str,
    volume_id: str,
    update: ManuscriptVolumeCreate,
    store: WritingDataStore = Depends(get_data_store),
) -> ManuscriptVolume:
    require_project(project_id, store)
    return store.update_manuscript_volume(project_id, volume_id, update)


@router.delete("/projects/{project_id}/manuscript/volumes/{volume_id}", status_code=204)
def delete_volume(
    project_id: str, volume_id: str, store: WritingDataStore = Depends(get_data_store)
) -> Response:
    require_project(project_id, store)
    if not store.delete_manuscript_volume(project_id, volume_id):
        raise ResourceNotFoundError("Manuscript volume not found.")
    return Response(status_code=204)


@router.put(
    "/projects/{project_id}/manuscript/chapters/{chapter_id}/volume",
    response_model=ChapterVolumeMembership,
)
def assign_volume(
    project_id: str,
    chapter_id: str,
    assignment: ChapterVolumeAssignment,
    store: WritingDataStore = Depends(get_data_store),
) -> ChapterVolumeMembership:
    require_project(project_id, store)
    return store.assign_chapter_volume(project_id, chapter_id, assignment.volume_id)
