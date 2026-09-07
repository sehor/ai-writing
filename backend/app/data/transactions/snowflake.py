"""Snowflake flows; the caller owns commit/rollback on the shared connection."""

import json
import sqlite3

from app.data.repositories.canon import CanonRepository
from app.data.repositories.narrative import NarrativeRepository
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.projects import ProjectRepository
from app.data.repositories.snowflake import SnowflakeRepository
from app.data.repositories.snowflake_records import SnowflakeRecordRepository
from app.models import (
    SnowflakeArtifact,
    SnowflakeArtifactHead,
    SnowflakeArtifactRevision,
    SnowflakeArtifactRevisionCreate,
    SnowflakeRecordDecisionResponse,
)
from app.outbox.events import snowflake_index_payload
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
