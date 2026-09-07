"""Writeback flows; the caller owns commit/rollback on the shared connection."""

import sqlite3

from app.data.helpers import utc_now
from app.data.repositories.canon import CanonRepository
from app.data.repositories.memory import MemoryRepository
from app.data.repositories.narrative import NarrativeRepository
from app.data.repositories.review import ReviewRepository
from app.data.repositories.scene_proposals import SceneProposalRepository
from app.models import (
    CanonEntityCreate,
    MemoryRecordCreate,
    NarrativeRelationCreate,
    StoryThreadCreate,
    StoryThreadEventCreate,
    WritebackProposal,
)
from app.review.writeback_apply import (
    WritebackTargetMissingError,
    WritebackVersionConflictError,
    apply_canon_update,
    validate_update_proposal,
)


def accept_writeback_proposal(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    proposal_id: str,
) -> WritebackProposal | None:
    """Apply one pending write-back and mark it accepted atomically.

    Update actions CAS-write the canon record (version conflict means the
    proposal is stale); create actions insert the canon/memory payload.
    Sibling pending update proposals for the same record are superseded.
    """
    review_repo = ReviewRepository(connection)
    canon_repo = CanonRepository(connection)
    memory_repo = MemoryRepository(connection)

    proposal = review_repo.get_writeback(project_id, proposal_id)
    if proposal is None:
        return None
    if proposal.status == "accepted":
        return proposal
    if proposal.status != "pending_review":
        raise ValueError("Write-back proposal is already reviewed.")

    if proposal.target == "story_thread_status":
        applied = _apply_story_thread_status_proposal(connection, project_id, proposal)
    elif proposal.target == "story_thread":
        applied = NarrativeRepository(connection).create_thread(
            project_id, StoryThreadCreate.model_validate(proposal.payload)
        )
    elif proposal.target == "story_thread_event":
        narrative = NarrativeRepository(connection)
        thread_id = proposal.target_record_id
        if not thread_id:
            thread_title = str(proposal.payload.get("thread_title", "")).strip().lower()
            matches = [
                thread
                for thread in narrative.list_threads(project_id)
                if thread.title.strip().lower() == thread_title
            ]
            if len(matches) != 1:
                raise WritebackTargetMissingError(thread_title or "unresolved-thread")
            thread_id = matches[0].id
        event_payload = {
            key: value
            for key, value in proposal.payload.items()
            if key not in {"thread_title", "scene_proposal_id"}
        }
        scene_proposal_id = str(proposal.payload.get("scene_proposal_id", "")).strip()
        if scene_proposal_id:
            scene_proposal = SceneProposalRepository(connection).get(project_id, scene_proposal_id)
            if scene_proposal is None or not scene_proposal.applied_scene_id:
                raise WritebackTargetMissingError(scene_proposal_id)
            event_payload["scene_id"] = scene_proposal.applied_scene_id
        applied = narrative.add_thread_event(
            project_id, thread_id, StoryThreadEventCreate.model_validate(event_payload)
        )
    elif proposal.action == "update":
        applied = _apply_canon_update_proposal(canon_repo, project_id, proposal)
    elif proposal.target == "canon_entity":
        applied = canon_repo.create(
            project_id,
            CanonEntityCreate.model_validate(proposal.payload),
        )
    elif proposal.target == "narrative_relation":
        relation_payload = {
            key: value for key, value in proposal.payload.items() if key != "evidence"
        }
        applied = NarrativeRepository(connection).create_relation(
            project_id,
            NarrativeRelationCreate.model_validate(relation_payload),
        )
    else:
        applied = memory_repo.create(
            project_id,
            MemoryRecordCreate.model_validate(proposal.payload),
        )

    reviewed_at = utc_now()
    marked = review_repo.mark_writeback_accepted(
        project_id=project_id,
        proposal_id=proposal_id,
        applied_record_id=applied.id,
        reviewed_at=reviewed_at,
    )
    if marked == 0:
        raise ValueError("Write-back proposal is already reviewed.")
    if proposal.action == "update":
        # Sibling update proposals for the same record are now stale;
        # they must not be silently accepted afterwards.
        review_repo.supersede_pending_for_target(
            project_id=project_id,
            keep_proposal_id=proposal.id,
            target_record_id=proposal.target_record_id,
            reviewed_at=reviewed_at,
        )
    return review_repo.get_writeback(project_id, proposal_id)


def _apply_story_thread_status_proposal(
    connection: sqlite3.Connection,
    project_id: str,
    proposal: WritebackProposal,
):
    narrative = NarrativeRepository(connection)
    thread = next(
        (
            item
            for item in narrative.list_threads(project_id)
            if item.id == proposal.target_record_id
        ),
        None,
    )
    if thread is None:
        raise WritebackTargetMissingError(proposal.target_record_id)
    expected = str(proposal.payload.get("from_state", ""))
    proposed = str(proposal.payload.get("proposed_state", ""))
    if thread.status != expected:
        raise ValueError(
            f"StoryThread '{thread.id}' changed since the proposal was created "
            f"(expected status '{expected}', current status '{thread.status}')."
        )
    applied = narrative.set_thread_status(project_id, thread.id, proposed)
    if applied is None:
        raise WritebackTargetMissingError(proposal.target_record_id)
    return applied


def _apply_canon_update_proposal(
    canon_repo: CanonRepository,
    project_id: str,
    proposal: WritebackProposal,
):
    validate_update_proposal(proposal)
    current = canon_repo.get(project_id, proposal.target_record_id)
    if current is None:
        raise WritebackTargetMissingError(proposal.target_record_id)
    if current.version != proposal.expected_version:
        raise WritebackVersionConflictError(
            proposal.target_record_id,
            proposal.expected_version,
            current.version,
        )
    updated = apply_canon_update(
        current,
        proposal,
        new_version=current.version + 1,
        updated_at=utc_now(),
    )
    rowcount = canon_repo.apply_cas_update(updated, expected_version=current.version)
    if rowcount == 0:
        raise WritebackVersionConflictError(
            proposal.target_record_id,
            proposal.expected_version,
            current.version,
        )
    return updated
