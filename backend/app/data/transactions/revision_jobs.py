"""Revision jobs flows; the caller owns commit/rollback on the shared connection."""

import sqlite3

from app.data.repositories.manuscript import ManuscriptRepository
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.scenes import SceneRepository
from app.models import ManuscriptRevision
from app.outbox.events import (
    manuscript_revision_analysis_payload,
    manuscript_revision_index_payload,
)


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
