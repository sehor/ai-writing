from fastapi import APIRouter, Depends, HTTPException, Response, status
import sqlite3

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.outbox.http import apply_wiki_index_headers
from app.outbox.service import OutboxService, get_outbox_service
from app.models import (
    ManuscriptExportResponse,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalStatusUpdate,
    ManuscriptRevisionDiff,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
)
from app.services.manuscript_service import ManuscriptService


router = APIRouter(tags=["manuscript"])


@router.get(
    "/projects/{project_id}/manuscript/chapters",
    response_model=list[ManuscriptChapter],
)
def list_manuscript_chapters(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[ManuscriptChapter]:
    require_project(project_id, data_store)
    return data_store.list_manuscript_chapters(project_id)


@router.post(
    "/projects/{project_id}/manuscript/chapters",
    response_model=ManuscriptChapter,
    status_code=status.HTTP_201_CREATED,
)
def create_manuscript_chapter(
    project_id: str,
    chapter: ManuscriptChapterCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> ManuscriptChapter:
    require_project(project_id, data_store)
    try:
        return data_store.create_manuscript_chapter(project_id, chapter)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chapter sequence already exists for this project.",
        ) from exc


@router.put(
    "/projects/{project_id}/manuscript/chapters/{chapter_id}",
    response_model=ManuscriptChapter,
)
def update_manuscript_chapter(
    project_id: str,
    chapter_id: str,
    chapter: ManuscriptChapterUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> ManuscriptChapter:
    require_project(project_id, data_store)
    try:
        updated = data_store.update_manuscript_chapter(project_id, chapter_id, chapter)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chapter sequence already exists for this project.",
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript chapter not found.",
        )
    return updated


@router.delete(
    "/projects/{project_id}/manuscript/chapters/{chapter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_manuscript_chapter(
    project_id: str,
    chapter_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
):
    require_project(project_id, data_store)
    deleted = data_store.delete_manuscript_chapter(project_id, chapter_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript chapter not found.",
        )


@router.get(
    "/projects/{project_id}/manuscript/proposals",
    response_model=list[ManuscriptProposal],
)
def list_manuscript_proposals(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[ManuscriptProposal]:
    require_project(project_id, data_store)
    return data_store.list_manuscript_proposals(project_id)


@router.get(
    "/projects/{project_id}/manuscript/scenes",
    response_model=list[ManuscriptScene],
)
def list_manuscript_scenes(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[ManuscriptScene]:
    require_project(project_id, data_store)
    return data_store.list_manuscript_scenes(project_id)


@router.put(
    "/projects/{project_id}/manuscript/scenes/{scene_id}",
    response_model=ManuscriptScene,
)
def update_manuscript_scene(
    project_id: str,
    scene_id: str,
    update: ManuscriptSceneUpdate,
    response: Response,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
    outbox: OutboxService = Depends(get_outbox_service),
) -> ManuscriptScene:
    require_project(project_id, data_store)
    scene = service.update_scene(project_id, scene_id, update)
    apply_wiki_index_headers(response, outbox.process_pending(project_id))
    return scene


@router.get(
    "/projects/{project_id}/manuscript/export",
    response_model=ManuscriptExportResponse,
)
def export_manuscript(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
) -> ManuscriptExportResponse:
    require_project(project_id, data_store)
    return service.export(project_id)


@router.get(
    "/projects/{project_id}/manuscript/revisions",
    response_model=list[ManuscriptRevision],
)
def list_manuscript_revisions(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[ManuscriptRevision]:
    require_project(project_id, data_store)
    return data_store.list_manuscript_revisions(project_id)


@router.get(
    "/projects/{project_id}/manuscript/revisions/{left_revision_id}/diff/{right_revision_id}",
    response_model=ManuscriptRevisionDiff,
)
def diff_manuscript_revisions(
    project_id: str,
    left_revision_id: str,
    right_revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
) -> ManuscriptRevisionDiff:
    require_project(project_id, data_store)
    return service.diff_revisions(project_id, left_revision_id, right_revision_id)


@router.post(
    "/projects/{project_id}/manuscript/revisions/{revision_id}/restore",
    response_model=ManuscriptScene,
)
def restore_manuscript_revision(
    project_id: str,
    revision_id: str,
    response: Response,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
    outbox: OutboxService = Depends(get_outbox_service),
) -> ManuscriptScene:
    require_project(project_id, data_store)
    scene = service.restore_revision(project_id, revision_id)
    apply_wiki_index_headers(response, outbox.process_pending(project_id))
    return scene


@router.post(
    "/projects/{project_id}/manuscript/proposals/from-scene/{scene_id}",
    response_model=ManuscriptProposal,
    status_code=status.HTTP_201_CREATED,
)
def create_manuscript_proposal_from_scene(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    return service.generate_local_proposal(project_id, scene_id)


@router.post(
    "/projects/{project_id}/manuscript/proposals/from-scene/{scene_id}/provider",
    response_model=ManuscriptProposal,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_manuscript_proposal_from_scene(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    return service.generate_provider_proposal(project_id, scene_id)


@router.put(
    "/projects/{project_id}/manuscript/proposals/{proposal_id}/status",
    response_model=ManuscriptProposal,
)
def update_manuscript_proposal_status(
    project_id: str,
    proposal_id: str,
    update: ManuscriptProposalStatusUpdate,
    response: Response,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
    outbox: OutboxService = Depends(get_outbox_service),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    proposal = service.update_proposal_status(project_id, proposal_id, update.status)
    apply_wiki_index_headers(response, outbox.process_pending(project_id))
    return proposal
