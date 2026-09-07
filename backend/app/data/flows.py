"""Cross-aggregate transactional flows (P2-03).

Each function coordinates several repositories against ONE open sqlite3
connection - the connection a SqliteUnitOfWork manages or the one a
caller handed to the store facade - and preserves the exact semantics of
the pre-split mixin implementations: idempotency keys, state-machine
transitions, supersede behavior and returned values.

Functions here never commit; the transaction boundary belongs to
SqliteUnitOfWork.
"""

import json
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
    SceneProposalQualityError,
    SceneSequenceConflictError,
    merge_required_canon,
    step_from_source_ref,
)
from app.data.repositories.scenes import SceneRepository
from app.data.repositories.snowflake import SnowflakeRepository
from app.data.repositories.snowflake_records import SnowflakeRecordRepository
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
    SnowflakeArtifactHead,
    SnowflakeArtifactRevision,
    SnowflakeArtifactRevisionCreate,
    SnowflakeRecordDecisionResponse,
    StoryThreadCreate,
    StoryThreadEventCreate,
    WritebackProposal,
)
from app.snowflake.dependencies import downstream_steps
from app.snowflake.validators import (
    validate_scene_record_set_context,
    validate_snowflake_payload,
    validate_snowflake_record_payload,
)


class SnowflakeRevisionNotFoundError(LookupError):
    pass


class SnowflakeRevisionStateError(ValueError):
    pass


class SnowflakeHeadConflictError(ValueError):
    pass


class SnowflakeRevisionValidationError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__("Snowflake revision has blocking validation findings.")


def decide_snowflake_revision(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    revision_id: str,
    decision: str,
    expected_head_revision_id: str,
    review_reason: str = "",
) -> tuple[SnowflakeArtifactRevision, SnowflakeArtifactHead, list[int], str]:
    """Review a revision; acceptance is the sole Snowflake commit point."""
    snowflake = SnowflakeRepository(connection)
    revision = snowflake.get_revision(project_id, revision_id)
    if revision is None:
        raise SnowflakeRevisionNotFoundError("Snowflake revision not found.")
    head = snowflake.get_head(project_id, revision.step_number)
    if (
        decision == revision.status == "accepted"
        and head.accepted_revision_id == revision.id
        and expected_head_revision_id in {revision.base_head_revision_id, revision.id}
    ):
        return revision, head, [], ""
    if decision == "accepted" and (
        head.accepted_revision_id != expected_head_revision_id
        or revision.base_head_revision_id != expected_head_revision_id
    ):
        raise SnowflakeHeadConflictError(
            "Snowflake accepted head changed; reload the step before accepting this revision."
        )
    if revision.status == decision:
        return revision, head, [], ""
    if revision.status not in {"draft", "pending_review"}:
        raise SnowflakeRevisionStateError(
            f"Snowflake revision in status '{revision.status}' cannot be reviewed."
        )
    if decision == "rejected":
        rejected = snowflake.set_revision_status(
            project_id,
            revision_id,
            "rejected",
            review_reason=review_reason,
        )
        return rejected, head, [], ""
    if decision != "accepted":
        raise SnowflakeRevisionStateError(f"Unsupported Snowflake decision: {decision}")

    validation = validate_snowflake_payload(
        revision.step_number,
        revision.content,
        revision.structured_payload,
    )
    if validation.status == "failed":
        raise SnowflakeRevisionValidationError(validation)

    accepted = snowflake.set_revision_status(
        project_id,
        revision_id,
        "accepted",
        review_reason=review_reason,
    )
    accepted_head = snowflake.accept_revision(accepted)
    accepted_projection = SnowflakeArtifact(
        project_id=project_id,
        step_number=accepted.step_number,
        artifact=accepted.artifact_type,
        content=accepted.content,
    )
    snowflake.update_accepted_projection(accepted_projection)
    ProjectRepository(connection).advance_current_step(project_id, accepted.step_number)
    affected = list(downstream_steps(accepted.step_number))
    snowflake.mark_stale(
        project_id,
        tuple(affected),
        reason=f"Step {accepted.step_number} accepted head changed.",
        trigger_revision_id=accepted.id,
    )
    job_id = OutboxRepository(connection).insert(
        project_id=project_id,
        job_type="llm_wiki_ingest",
        aggregate_type="snowflake_artifact_revision",
        aggregate_id=accepted.id,
        payload=snowflake_index_payload(accepted_projection),
        idempotency_key=f"llm_wiki_ingest:snowflake_revision:{accepted.id}",
    )
    return accepted, accepted_head, affected, job_id


def decide_snowflake_record_revision(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    revision_id: str,
    decision: str,
    expected_revision_id: str,
    review_reason: str = "",
) -> SnowflakeRecordDecisionResponse:
    """Review one record and rebuild the derived accepted Artifact projection.

    Record heads are the source of truth for steps 6-9. The artifact revision
    created here is a deterministic snapshot for legacy readers, step progress,
    staleness propagation, and indexing only.
    """
    records = SnowflakeRecordRepository(connection)
    candidate = records.get_revision(project_id, revision_id)
    if candidate is None:
        raise LookupError("Snowflake record revision not found.")
    if candidate.status == decision == "accepted":
        head = records.get_head(project_id, candidate.step_number, candidate.record_id)
        if (
            head is not None
            and head.accepted_revision_id == candidate.id
            and expected_revision_id in {candidate.base_revision_id, candidate.id}
        ):
            return SnowflakeRecordDecisionResponse(revision=candidate, head=head)
    if decision == "accepted":
        validation = validate_snowflake_record_payload(candidate.step_number, candidate.payload)
        if validation.status == "failed":
            raise SnowflakeRevisionValidationError(validation)
        if candidate.step_number == 8:
            accepted = [
                record
                for record in records.list_accepted(project_id, 8)
                if record.record_id != candidate.record_id
            ]
            accepted.append(candidate)
            contextual = validate_scene_record_set_context(
                accepted,
                CanonRepository(connection).list(project_id),
                NarrativeRepository(connection).list_threads(project_id),
            )
            if contextual.status == "failed":
                raise SnowflakeRevisionValidationError(contextual)

    revision, record_head = records.decide(
        project_id,
        revision_id,
        decision=decision,
        expected_revision_id=expected_revision_id,
        review_reason=review_reason,
    )
    if decision != "accepted":
        return SnowflakeRecordDecisionResponse(revision=revision, head=record_head)

    accepted_records = records.list_accepted(project_id, revision.step_number)
    for accepted_record in accepted_records:
        validation = validate_snowflake_record_payload(
            accepted_record.step_number, accepted_record.payload
        )
        if validation.status == "failed":
            raise SnowflakeRevisionValidationError(validation)

    snapshot = {
        "records": [
            {
                "record_id": record.record_id,
                "revision_id": record.id,
                "position": record.position,
                "payload": record.payload,
            }
            for record in accepted_records
        ]
    }
    content = json.dumps(snapshot, ensure_ascii=False, indent=2)
    snowflake = SnowflakeRepository(connection)
    projection = snowflake.create_revision(
        project_id,
        SnowflakeArtifactRevisionCreate(
            step_number=revision.step_number,
            content=content,
            structured_payload=snapshot,
            source="derived",
        ),
        status="draft",
        source="derived",
    )
    projection = snowflake.set_revision_status(
        project_id,
        projection.id,
        "accepted",
        review_reason=f"Derived from accepted record revision {revision.id}.",
    )
    snowflake.accept_revision(projection)
    accepted_projection = SnowflakeArtifact(
        project_id=project_id,
        step_number=projection.step_number,
        artifact=projection.artifact_type,
        content=projection.content,
    )
    snowflake.update_accepted_projection(accepted_projection)
    ProjectRepository(connection).advance_current_step(project_id, projection.step_number)
    affected = downstream_steps(projection.step_number)
    snowflake.mark_stale(
        project_id,
        affected,
        reason=f"Step {projection.step_number} accepted record set changed.",
        trigger_revision_id=revision.id,
    )
    OutboxRepository(connection).insert(
        project_id=project_id,
        job_type="llm_wiki_ingest",
        aggregate_type="snowflake_record_snapshot",
        aggregate_id=projection.id,
        payload=snowflake_index_payload(accepted_projection),
        idempotency_key=f"llm_wiki_ingest:snowflake_record_snapshot:{projection.id}",
    )
    return SnowflakeRecordDecisionResponse(revision=revision, head=record_head)


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
        if proposal.blocking_errors:
            raise SceneProposalQualityError(
                f"Scene proposal '{proposal.id}' is blocked: " + "; ".join(proposal.blocking_errors)
            )
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
                outcome=proposal.outcome,
                required_canon=merge_required_canon(proposal),
                forbidden_facts=proposal.forbidden_fact_refs,
                information_delta=proposal.information_delta,
                character_state_delta=proposal.character_state_delta,
                story_thread_actions=proposal.story_thread_actions,
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
