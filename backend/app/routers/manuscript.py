from difflib import unified_diff

from fastapi import APIRouter, Depends, HTTPException, status
import sqlite3

from app.agents import DeepSeekSettings, WorkflowNotConfiguredError, build_provider_scene_draft
from app.cognition.interfaces import WritingScope
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store, utc_now
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import (
    LlmWiki,
    WikiContextQuery,
    WikiSourceDocument,
)
from app.manuscript_export import build_export_markdown
from app.models import (
    ManuscriptExportResponse,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalCreate,
    ManuscriptProposalStatusUpdate,
    ManuscriptRevisionDiff,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
)
from app.routers.scenes import (
    build_compile_checklist,
    build_compile_context,
    build_scene_draft,
)


router = APIRouter(tags=["manuscript"])


def require_project(project_id: str, data_store: WritingDataStore) -> None:
    if not data_store.project_exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )


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
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> ManuscriptScene:
    require_project(project_id, data_store)
    scene = data_store.update_manuscript_scene(project_id, scene_id, update)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Accepted manuscript scene not found.",
        )
    ingest_latest_manuscript_revision(project_id, scene.scene_id, data_store, llm_wiki)
    return scene


@router.get(
    "/projects/{project_id}/manuscript/export",
    response_model=ManuscriptExportResponse,
)
def export_manuscript(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> ManuscriptExportResponse:
    require_project(project_id, data_store)
    project = data_store.get_project(project_id)
    scenes = data_store.list_manuscript_scenes(project_id)
    scene_contracts = {
        scene.id: scene
        for scene in data_store.list_scene_contracts(project_id)
    }
    chapters = data_store.list_manuscript_chapters(project_id)
    chapter_order = {chapter.id: chapter.sequence for chapter in chapters}
    ordered_scene_pairs = sorted(
        [
            (scene, scene_contracts.get(scene.scene_id))
            for scene in scenes
        ],
        key=lambda pair: (
            chapter_order.get(pair[1].chapter_id, 9999) if pair[1] else 9999,
            pair[1].sequence if pair[1] else 9999,
            pair[0].title,
        ),
    )
    title = project.title if project else project_id
    content = build_export_markdown(title, chapters, ordered_scene_pairs)
    return ManuscriptExportResponse(
        project_id=project_id,
        title=title,
        scene_count=len(ordered_scene_pairs),
        content=content,
        generated_at=utc_now(),
    )


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
) -> ManuscriptRevisionDiff:
    require_project(project_id, data_store)
    left = data_store.get_manuscript_revision(project_id, left_revision_id)
    right = data_store.get_manuscript_revision(project_id, right_revision_id)
    if left is None or right is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )
    return ManuscriptRevisionDiff(
        project_id=project_id,
        left_revision_id=left.id,
        right_revision_id=right.id,
        left_title=f"{left.title} v{left.version}",
        right_title=f"{right.title} v{right.version}",
        diff_lines=list(
            unified_diff(
                left.content.splitlines(),
                right.content.splitlines(),
                fromfile=f"{left.title} v{left.version}",
                tofile=f"{right.title} v{right.version}",
                lineterm="",
            )
        ),
    )


@router.post(
    "/projects/{project_id}/manuscript/revisions/{revision_id}/restore",
    response_model=ManuscriptScene,
)
def restore_manuscript_revision(
    project_id: str,
    revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> ManuscriptScene:
    require_project(project_id, data_store)
    scene = data_store.restore_manuscript_revision(project_id, revision_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )
    ingest_latest_manuscript_revision(project_id, scene.scene_id, data_store, llm_wiki)
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
    cognition: CognitionRegistry = Depends(get_cognition_registry),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    scene = data_store.get_scene_contract(project_id, scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )

    project = data_store.get_project(project_id)
    cognition_context = cognition.prepare_context(
        build_project_snapshot(project_id, data_store),
        WritingScope(kind="scene", ref=scene_id, instruction=scene.title),
    )
    llm_wiki_context = llm_wiki.retrieve_context(
        WikiContextQuery(
            project_id=project_id,
            snowflake_step=10,
            instruction=scene.title,
            scope=scene.id,
            story_position=scene.sequence,
            spoiler_horizon=scene.sequence,
        )
    )
    context = build_compile_context(
        project.title if project else project_id,
        scene,
        data_store.list_canon_entities(project_id),
        data_store.list_memory_records(project_id),
        data_store.list_snowflake_artifacts(project_id),
        cognition_context,
        llm_wiki_context,
    )
    proposal = ManuscriptProposalCreate(
        scene_id=scene.id,
        title=f"{scene.sequence}. {scene.title}",
        content=build_scene_draft(scene),
        context=context,
        checklist=build_compile_checklist(),
    )
    return data_store.create_manuscript_proposal(project_id, proposal)


@router.post(
    "/projects/{project_id}/manuscript/proposals/from-scene/{scene_id}/provider",
    response_model=ManuscriptProposal,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_manuscript_proposal_from_scene(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    scene = data_store.get_scene_contract(project_id, scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )

    try:
        settings = DeepSeekSettings.from_env()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"DeepSeek environment is invalid: {exc}",
        ) from exc
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="DeepSeek provider is not configured.",
        )

    project = data_store.get_project(project_id)
    cognition_context = cognition.prepare_context(
        build_project_snapshot(project_id, data_store),
        WritingScope(kind="scene", ref=scene_id, instruction=scene.title),
    )
    llm_wiki_context = llm_wiki.retrieve_context(
        WikiContextQuery(
            project_id=project_id,
            snowflake_step=10,
            instruction=scene.title,
            scope=scene.id,
            story_position=scene.sequence,
            spoiler_horizon=scene.sequence,
        )
    )
    context = build_compile_context(
        project.title if project else project_id,
        scene,
        data_store.list_canon_entities(project_id),
        data_store.list_memory_records(project_id),
        data_store.list_snowflake_artifacts(project_id),
        cognition_context,
        llm_wiki_context,
    )
    try:
        content = build_provider_scene_draft(settings, context)
    except WorkflowNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider manuscript generation failed: {exc}",
        ) from exc

    proposal = ManuscriptProposalCreate(
        scene_id=scene.id,
        title=f"{scene.sequence}. {scene.title} provider draft",
        content=content,
        context=context,
        checklist=[
            *build_compile_checklist(),
            "Provider draft is reviewed before accepting into Manuscript.",
        ],
    )
    return data_store.create_manuscript_proposal(project_id, proposal)


@router.put(
    "/projects/{project_id}/manuscript/proposals/{proposal_id}/status",
    response_model=ManuscriptProposal,
)
def update_manuscript_proposal_status(
    project_id: str,
    proposal_id: str,
    update: ManuscriptProposalStatusUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> ManuscriptProposal:
    require_project(project_id, data_store)
    if update.status == "accepted":
        scene = data_store.accept_manuscript_proposal(project_id, proposal_id)
        proposal = data_store.get_manuscript_proposal(project_id, proposal_id)
        if scene is None or proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript proposal not found.",
            )
        ingest_latest_manuscript_revision(
            project_id,
            scene.scene_id,
            data_store,
            llm_wiki,
        )
        return proposal

    proposal = data_store.update_manuscript_proposal_status(
        project_id,
        proposal_id,
        update.status,
    )
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript proposal not found.",
        )
    return proposal


def ingest_latest_manuscript_revision(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore,
    llm_wiki: LlmWiki,
) -> None:
    revisions = [
        revision
        for revision in data_store.list_manuscript_revisions(project_id)
        if revision.scene_id == scene_id
    ]
    if not revisions:
        return
    latest = max(revisions, key=lambda revision: revision.version)
    previous = max(
        (
            revision
            for revision in revisions
            if revision.version < latest.version
        ),
        key=lambda revision: revision.version,
        default=None,
    )
    scene = data_store.get_scene_contract(project_id, scene_id)
    llm_wiki.ingest(
        WikiSourceDocument(
            project_id=project_id,
            source_kind="manuscript_revision",
            source_ref=f"manuscript_revision:{latest.id}",
            title=latest.title,
            content=latest.content,
            snowflake_step=10,
            artifact_type="manuscript",
            knowledge_class="observed",
            version=latest.version,
            supersedes=(
                f"manuscript_revision:{previous.id}"
                if previous is not None
                else ""
            ),
            scope=scene_id,
            story_position=scene.sequence if scene is not None else None,
        )
    )
