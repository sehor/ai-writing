from fastapi import APIRouter, Depends, HTTPException, Response, status
import sqlite3

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.outbox.dispatcher import (
    OutboxDispatcher,
    get_outbox_dispatcher,
    wake_outbox_best_effort,
)
from app.models import (
    LegacyManuscriptImportCreate,
    ManuscriptExportResponse,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalAcceptance,
    ManuscriptProposalStatusUpdate,
    ManuscriptRevisionDiff,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
)
from app.analysis.models import ConsistencyReport
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
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
    dispatcher: OutboxDispatcher = Depends(get_outbox_dispatcher),
) -> ManuscriptScene:
    require_project(project_id, data_store)
    scene = service.update_scene(project_id, scene_id, update)
    # P1-01/P1-03: a manual save commits a formal revision whose post-commit
    # pipeline (wiki + both analyses) was enqueued in the same transaction;
    # the background dispatcher runs it, not this request.
    wake_outbox_best_effort(
        dispatcher,
        operation="manuscript_manual_save",
        project_id=project_id,
    )
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
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
    dispatcher: OutboxDispatcher = Depends(get_outbox_dispatcher),
) -> ManuscriptScene:
    require_project(project_id, data_store)
    scene = service.restore_revision(project_id, revision_id)
    # P1-01/P1-03: the restored revision re-enters the post-commit pipeline;
    # its jobs were enqueued transactionally and run in the background.
    wake_outbox_best_effort(
        dispatcher,
        operation="manuscript_restore_revision",
        project_id=project_id,
    )
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


@router.post(
    "/projects/{project_id}/manuscript/proposals/from-legacy-snowflake/{revision_id}",
    response_model=ManuscriptProposal,
    status_code=status.HTTP_201_CREATED,
)
def create_manuscript_proposal_from_legacy_snowflake(
    project_id: str,
    revision_id: str,
    selection: LegacyManuscriptImportCreate,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    return service.import_legacy_snowflake_draft(project_id, revision_id, selection)


@router.post(
    "/projects/{project_id}/manuscript/proposals/{proposal_id}/accept",
    response_model=ManuscriptProposal,
)
def accept_edited_manuscript_proposal(
    project_id: str,
    proposal_id: str,
    draft: ManuscriptProposalAcceptance,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
    dispatcher: OutboxDispatcher = Depends(get_outbox_dispatcher),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    proposal = service.update_proposal_status(project_id, proposal_id, "accepted", draft=draft)
    wake_outbox_best_effort(dispatcher, operation="accept_edited_draft", project_id=project_id)
    return proposal


@router.post(
    "/projects/{project_id}/manuscript/proposals/{proposal_id}/consistency",
    response_model=ConsistencyReport,
)
def preview_manuscript_proposal_consistency(
    project_id: str,
    proposal_id: str,
    draft: ManuscriptProposalAcceptance,
    data_store: WritingDataStore = Depends(get_data_store),
    service: ManuscriptService = Depends(),
) -> ConsistencyReport:
    require_project(project_id, data_store)
    return service.preview_proposal_consistency(project_id, proposal_id, draft)


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
    dispatcher: OutboxDispatcher = Depends(get_outbox_dispatcher),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    deprecation_headers = {
        "Deprecation": "true",
        "Link": (
            f"</api/projects/{project_id}/manuscript/proposals/{proposal_id}/accept>; "
            'rel="successor-version"'
        ),
    }
    try:
        proposal = service.update_proposal_status(project_id, proposal_id, update.status)
    except HTTPException as exc:
        if update.status == "accepted":
            exc.headers = {**(exc.headers or {}), **deprecation_headers}
        raise
    if update.status == "accepted":
        response.headers.update(deprecation_headers)
    # P1-07/P1-03: acceptance enqueued wiki + consistency + write-back jobs
    # transactionally; the background dispatcher executes them after this
    # response has been sent.
    wake_outbox_best_effort(
        dispatcher,
        operation="manuscript_proposal_status",
        project_id=project_id,
    )
    return proposal
