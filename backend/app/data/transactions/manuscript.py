"""Manuscript flows; the caller owns commit/rollback on the shared connection."""

import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.data.repositories.manuscript import ManuscriptRepository
from app.data.transactions.revision_jobs import enqueue_committed_revision_jobs
from app.models import (
    ManuscriptProposalAcceptance,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
)


def accept_manuscript_proposal(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    proposal_id: str,
    draft: ManuscriptProposalAcceptance | None = None,
) -> ManuscriptScene | None:
    """Accept one pending proposal: scene upsert + revision + jobs + supersede.

    Creates the accepted scene row and its immutable first/next revision,
    enqueues the wiki index job plus both analysis jobs, marks this
    proposal accepted and supersedes sibling pending proposals for the
    same scene - all inside the caller's transaction.
    """
    now = utc_now()
    manuscripts = ManuscriptRepository(connection)

    proposal = manuscripts.get_proposal(project_id, proposal_id)
    if proposal is None:
        return None
    if proposal.status == "accepted":
        return manuscripts.get_scene(project_id, proposal.scene_id)
    if proposal.status != "pending_review":
        return None

    current_version = manuscripts.get_scene_version(project_id, proposal.scene_id)
    if draft is not None and draft.expected_scene_version != (current_version or 0):
        raise ValueError(
            "The manuscript scene changed while this draft was being edited. Reload before accepting."
        )
    version = current_version + 1 if current_version is not None else 1
    scene = ManuscriptScene(
        id=make_record_id(
            f"{project_id}-manuscript-{proposal.scene_id}",
            manuscripts.list_scene_ids(),
        )
        if current_version is None
        else f"manuscript-{proposal.scene_id}",
        project_id=project_id,
        scene_id=proposal.scene_id,
        proposal_id=proposal.id,
        title=draft.title if draft is not None else proposal.title,
        content=draft.content if draft is not None else proposal.content,
        version=version,
        accepted_at=now,
    )
    revision = ManuscriptRevision(
        id=make_record_id(
            f"{project_id}-revision-{proposal.scene_id}-v{version}",
            manuscripts.list_revision_ids(),
        ),
        project_id=project_id,
        scene_id=proposal.scene_id,
        proposal_id=proposal.id,
        title=scene.title,
        content=scene.content,
        version=version,
        created_at=now,
    )
    manuscripts.upsert_scene(scene)
    manuscripts.insert_revision(revision)
    enqueue_committed_revision_jobs(connection, revision=revision)
    manuscripts.set_proposal_status(
        project_id=project_id,
        proposal_id=proposal_id,
        status="accepted",
        reviewed_at=now,
    )
    # Sibling pending proposals for the same scene are stale now;
    # supersede them instead of leaving a second accept ambiguous.
    manuscripts.supersede_pending_for_scene(
        project_id=project_id,
        scene_id=proposal.scene_id,
        except_proposal_id=proposal_id,
        reviewed_at=now,
    )
    return manuscripts.get_scene(project_id, proposal.scene_id)


def restore_manuscript_revision(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    revision_id: str,
) -> ManuscriptScene | None:
    """Restore an old revision as the newest scene version (+ full pipeline)."""
    now = utc_now()
    manuscripts = ManuscriptRepository(connection)

    source_revision = manuscripts.get_revision(project_id, revision_id)
    if source_revision is None:
        return None
    current_version = manuscripts.get_scene_version(project_id, source_revision.scene_id)
    version = current_version + 1 if current_version is not None else 1
    scene = ManuscriptScene(
        id=make_record_id(
            f"{project_id}-manuscript-{source_revision.scene_id}",
            manuscripts.list_scene_ids(),
        )
        if current_version is None
        else f"{project_id}-manuscript-{source_revision.scene_id}",
        project_id=project_id,
        scene_id=source_revision.scene_id,
        proposal_id=source_revision.proposal_id,
        title=source_revision.title,
        content=source_revision.content,
        version=version,
        accepted_at=now,
    )
    restored_revision = ManuscriptRevision(
        id=make_record_id(
            f"{project_id}-revision-{source_revision.scene_id}-v{version}",
            manuscripts.list_revision_ids(),
        ),
        project_id=project_id,
        scene_id=source_revision.scene_id,
        proposal_id=source_revision.proposal_id,
        title=source_revision.title,
        content=source_revision.content,
        version=version,
        created_at=now,
    )
    manuscripts.upsert_scene(scene)
    manuscripts.insert_revision(restored_revision)
    enqueue_committed_revision_jobs(connection, revision=restored_revision)
    return manuscripts.get_scene(project_id, source_revision.scene_id)


def update_manuscript_scene(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    scene_id: str,
    update: ManuscriptSceneUpdate,
) -> ManuscriptScene | None:
    """Manual scene edit: bump version, file a revision, run the pipeline."""
    now = utc_now()
    manuscripts = ManuscriptRepository(connection)

    current_scene = manuscripts.get_scene(project_id, scene_id)
    if current_scene is None:
        return None
    if update.expected_scene_version != current_scene.version:
        raise ValueError(
            f"The manuscript scene changed from v{update.expected_scene_version} "
            f"to v{current_scene.version}. Review the latest text before saving."
        )
    version = current_scene.version + 1
    manuscripts.update_scene_fields(
        project_id=project_id,
        scene_id=scene_id,
        title=update.title,
        content=update.content,
        version=version,
        accepted_at=now,
    )
    revision = ManuscriptRevision(
        id=make_record_id(
            f"{project_id}-revision-{scene_id}-v{version}",
            manuscripts.list_revision_ids(),
        ),
        project_id=project_id,
        scene_id=scene_id,
        proposal_id=current_scene.proposal_id,
        title=update.title,
        content=update.content,
        version=version,
        created_at=now,
    )
    manuscripts.insert_revision(revision)
    enqueue_committed_revision_jobs(connection, revision=revision)
    return manuscripts.get_scene(project_id, scene_id)
