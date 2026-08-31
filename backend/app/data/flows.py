"""Cross-aggregate transactional flows (P2-03).

Each function coordinates several repositories against ONE open sqlite3
connection - the connection a SqliteUnitOfWork manages or the one a
caller handed to the store facade - and preserves the exact semantics of
the pre-split mixin implementations: idempotency keys, state-machine
transitions, supersede behavior and returned values.

Functions here never commit; the transaction boundary belongs to
SqliteUnitOfWork.
"""

from hashlib import sha256
import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.data.repositories.canon import CanonRepository
from app.data.repositories.manuscript import ManuscriptRepository
from app.data.repositories.memory import MemoryRepository
from app.data.repositories.narrative import NarrativeRepository
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.projects import ProjectRepository
from app.data.repositories.review import ReviewRepository
from app.data.repositories.scene_proposals import (
    SceneChapterMissingError,
    SceneProposalNotFoundError,
    SceneProposalReviewedError,
    SceneProposalRepository,
    SceneSequenceConflictError,
    merge_required_canon,
    step_from_source_ref,
)
from app.data.repositories.scenes import SceneRepository
from app.data.repositories.snowflake import SnowflakeRepository
from app.models import (
    CanonEntityCreate,
    ManuscriptProposalAcceptance,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    MemoryRecordCreate,
    NarrativeRelationCreate,
    SceneContract,
    SceneContractCreate,
    SceneProposal,
    SnowflakeArtifact,
    WritebackProposal,
)
from app.outbox.handlers import (
    manuscript_revision_analysis_payload,
    manuscript_revision_index_payload,
    snowflake_index_payload,
)
from app.review.writeback_apply import (
    WritebackTargetMissingError,
    WritebackVersionConflictError,
    apply_canon_update,
    validate_update_proposal,
)


def enqueue_snowflake_index_job(
    connection: sqlite3.Connection,
    artifact: SnowflakeArtifact,
    advance_step_to: int | None = None,
) -> tuple[SnowflakeArtifact, str]:
    """Save a snowflake artifact and enqueue its wiki index job atomically."""
    saved = SnowflakeRepository(connection).save(artifact)
    if advance_step_to is not None:
        ProjectRepository(connection).advance_current_step(saved.project_id, advance_step_to)
    job_id = OutboxRepository(connection).insert(
        project_id=saved.project_id,
        job_type="llm_wiki_ingest",
        aggregate_type="snowflake_artifact",
        aggregate_id=f"{saved.project_id}:{saved.step_number}",
        payload=snowflake_index_payload(saved),
        # Content hash keeps the key stable per save event without
        # depending on clock precision between rapid saves.
        idempotency_key=(
            f"llm_wiki_ingest:snowflake:{saved.project_id}:"
            f"{saved.step_number}:"
            f"{sha256(saved.content.encode('utf-8')).hexdigest()[:16]}"
        ),
    )
    return saved, job_id


def enqueue_manuscript_revision_index_job(
    connection: sqlite3.Connection,
    *,
    revision: ManuscriptRevision,
) -> str:
    """Enqueue a wiki index job inside the caller's transaction.

    Resolves the superseded revision and the scene position from the
    same transaction so payload building cannot observe partial state.
    """
    manuscripts = ManuscriptRepository(connection)
    previous_id = None
    if revision.version > 1:
        previous_id = manuscripts.previous_revision_id(
            revision.project_id, revision.scene_id, revision.version - 1
        )
    story_position = SceneRepository(connection).get_sequence(
        revision.project_id, revision.scene_id
    )
    return OutboxRepository(connection).insert(
        project_id=revision.project_id,
        job_type="llm_wiki_ingest",
        aggregate_type="manuscript_revision",
        aggregate_id=revision.id,
        payload=manuscript_revision_index_payload(revision, previous_id, story_position),
        idempotency_key=f"llm_wiki_ingest:manuscript_revision:{revision.id}",
    )


def enqueue_manuscript_revision_analysis_jobs(
    connection: sqlite3.Connection,
    *,
    revision: ManuscriptRevision,
) -> tuple[str, str]:
    """Enqueue post-acceptance analysis jobs inside the caller's transaction (P1-07).

    One consistency-report job and one deterministic write-back analysis
    job per revision. Both are keyed by the immutable revision id, so a
    retried accept or a re-dispatch can never duplicate them.
    """
    outbox = OutboxRepository(connection)
    base_payload = manuscript_revision_analysis_payload(revision)
    consistency_job_id = outbox.insert(
        project_id=revision.project_id,
        job_type="consistency_analysis",
        aggregate_type="manuscript_revision",
        aggregate_id=revision.id,
        payload=base_payload,
        idempotency_key=f"consistency_analysis:manuscript_revision:{revision.id}",
    )
    writeback_job_id = outbox.insert(
        project_id=revision.project_id,
        job_type="writeback_analysis",
        aggregate_type="manuscript_revision",
        aggregate_id=revision.id,
        payload={**base_payload, "processor": "local_writeback"},
        idempotency_key=(f"writeback_analysis:manuscript_revision:{revision.id}:local_writeback"),
    )
    return consistency_job_id, writeback_job_id


def enqueue_committed_revision_jobs(
    connection: sqlite3.Connection,
    *,
    revision: ManuscriptRevision,
) -> tuple[str, str, str, str]:
    """Enqueue the full post-commit pipeline for one committed revision (P1-01).

    Every path that files a formal ManuscriptRevision - proposal accept,
    manual scene edit, revision restore, and later Copilot Apply - must go
    through this single helper so no committed content can skip wiki
    indexing, consistency analysis or write-back analysis. Jobs are keyed by
    the immutable revision id, so replaying the helper never duplicates them.
    """
    index_job_id = enqueue_manuscript_revision_index_job(connection, revision=revision)
    consistency_job_id, writeback_job_id = enqueue_manuscript_revision_analysis_jobs(
        connection, revision=revision
    )
    clp_job_id = OutboxRepository(connection).insert(
        project_id=revision.project_id,
        job_type="clp_extraction",
        aggregate_type="manuscript_revision",
        aggregate_id=revision.id,
        payload=manuscript_revision_analysis_payload(revision),
        idempotency_key=f"clp_extraction:manuscript_revision:{revision.id}",
    )
    return index_job_id, consistency_job_id, writeback_job_id, clp_job_id


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


def accept_scene_proposals(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    proposal_ids: list[str],
) -> tuple[list[SceneContract], list[SceneProposal]]:
    """Batch-accept pending proposals into scene contracts.

    One transaction creates every contract and marks every proposal
    accepted; any validation failure raises before a single insert,
    and an insert failure rolls the whole batch back.
    """
    proposals_repo = SceneProposalRepository(connection)
    scenes_repo = SceneRepository(connection)
    chapters_repo = ManuscriptRepository(connection)

    proposals = [proposals_repo.get(project_id, pid) for pid in proposal_ids]
    missing = [pid for pid, proposal in zip(proposal_ids, proposals) if proposal is None]
    if missing:
        raise SceneProposalNotFoundError(missing[0])

    blocked = [
        proposal for proposal in proposals if proposal.status not in ("pending_review", "accepted")
    ]
    if blocked:
        # Rejected / superseded proposals are terminal; accepting
        # them would violate the unified review state machine.
        first = blocked[0]
        raise SceneProposalReviewedError(
            f"Scene proposal '{first.id}' is already reviewed "
            f"(status '{first.status}'); accepting it again is not allowed."
        )

    ordered = sorted(
        (proposal for proposal in proposals if proposal.status == "pending_review"),
        key=lambda proposal: (proposal.sequence, proposal.id),
    )
    already_accepted = [proposal for proposal in proposals if proposal.status == "accepted"]

    # Pre-validation before any insert so nothing partial is written.
    chapter_ids = {chapter.id for chapter in chapters_repo.list_chapters(project_id)}
    seen_sequences: dict[int, str] = {}
    for proposal in ordered:
        if proposal.sequence in seen_sequences:
            raise SceneSequenceConflictError(
                f"Proposals '{seen_sequences[proposal.sequence]}' and "
                f"'{proposal.id}' both use scene sequence {proposal.sequence}."
            )
        seen_sequences[proposal.sequence] = proposal.id
        if proposal.chapter_id and proposal.chapter_id not in chapter_ids:
            raise SceneChapterMissingError(
                f"Scene proposal '{proposal.id}' references chapter "
                f"'{proposal.chapter_id}', which does not belong to this project."
            )

    existing_sequences = scenes_repo.list_sequences(project_id)
    clashes = sorted(set(seen_sequences) & existing_sequences)
    if clashes:
        raise SceneSequenceConflictError(
            "Scene sequence already exists for this project: "
            + ", ".join(str(number) for number in clashes)
            + "."
        )

    now = utc_now()
    created_scenes = []
    for proposal in ordered:
        scene = scenes_repo.insert(
            project_id,
            SceneContractCreate(
                chapter_id=proposal.chapter_id,
                sequence=proposal.sequence,
                title=proposal.title,
                pov=proposal.pov,
                goal=proposal.goal,
                conflict=proposal.conflict,
                turning_point=proposal.turning_point,
                required_canon=merge_required_canon(proposal),
                forbidden_facts=proposal.forbidden_fact_refs,
                open_threads=proposal.open_threads,
                source_artifact_step=step_from_source_ref(proposal.source_ref),
            ),
        )
        created_scenes.append(scene)
        updated = proposals_repo.mark_accepted(
            project_id=project_id,
            proposal_id=proposal.id,
            applied_scene_id=scene.id,
            reviewed_at=now,
        )
        if updated == 0:
            raise SceneProposalReviewedError(
                f"Scene proposal '{proposal.id}' changed concurrently."
            )

    accepted_ids = [proposal.id for proposal in ordered]
    accepted_ids.extend(proposal.id for proposal in already_accepted)
    accepted = [proposals_repo.get(project_id, pid) for pid in accepted_ids]
    replayed_scenes = [
        scenes_repo.get(project_id, proposal.applied_scene_id)
        for proposal in already_accepted
        if proposal.applied_scene_id
    ]
    scenes = created_scenes + [scene for scene in replayed_scenes if scene]
    return scenes, [proposal for proposal in accepted if proposal is not None]


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
