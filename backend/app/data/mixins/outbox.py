import json
import sqlite3
from hashlib import sha256

from app.data.helpers import make_record_id, utc_now
from app.models import ManuscriptRevision, SnowflakeArtifact
from app.outbox.handlers import (
    manuscript_revision_index_payload,
    snowflake_index_payload,
)
from app.outbox.models import OutboxJob, OutboxJobStatus


def outbox_job_from_row(row: sqlite3.Row) -> OutboxJob:
    return OutboxJob(
        id=row["id"],
        project_id=row["project_id"],
        job_type=row["job_type"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        payload=json.loads(row["payload_json"]),
        status=row["status"],
        attempt_count=row["attempt_count"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


class OutboxDataMixin:
    def insert_outbox_job(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        job_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
        idempotency_key: str,
    ) -> str:
        """Insert an outbox job inside the caller's transaction.

        Returns the job id. If a job with the same idempotency key already
        exists, its id is returned without inserting a duplicate.
        """
        existing = connection.execute(
            "SELECT id FROM outbox_jobs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            return existing["id"]
        job_id = make_record_id(
            f"outbox-{job_type}-{aggregate_id}",
            {row["id"] for row in connection.execute("SELECT id FROM outbox_jobs").fetchall()},
        )
        connection.execute(
            """
            INSERT INTO outbox_jobs (
                id, project_id, job_type, aggregate_type, aggregate_id,
                payload_json, idempotency_key, status, attempt_count,
                last_error, created_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, '', ?, '')
            """,
            (
                job_id,
                project_id,
                job_type,
                aggregate_type,
                aggregate_id,
                json.dumps(payload, ensure_ascii=False),
                idempotency_key,
                utc_now(),
            ),
        )
        return job_id

    def enqueue_snowflake_index_job(
        self,
        artifact: SnowflakeArtifact,
        advance_step_to: int | None = None,
    ) -> tuple[SnowflakeArtifact, str]:
        """Save a snowflake artifact and enqueue its wiki index job atomically."""
        with self.connect() as connection:
            saved = self.save_snowflake_artifact(artifact, connection)
            if advance_step_to is not None:
                self.advance_project_current_step(saved.project_id, advance_step_to, connection)
            job_id = self.insert_outbox_job(
                connection,
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
        self,
        connection: sqlite3.Connection,
        *,
        revision: ManuscriptRevision,
    ) -> str:
        """Enqueue a wiki index job inside the caller's transaction.

        Resolves the superseded revision and the scene position from the
        same transaction so payload building cannot observe partial state.
        """
        previous_id = None
        if revision.version > 1:
            prev_row = connection.execute(
                """
                SELECT id FROM manuscript_revisions
                WHERE project_id = ? AND scene_id = ? AND version = ?
                """,
                (revision.project_id, revision.scene_id, revision.version - 1),
            ).fetchone()
            previous_id = prev_row["id"] if prev_row else None
        seq_row = connection.execute(
            """
            SELECT sequence FROM scene_contracts
            WHERE project_id = ? AND id = ?
            """,
            (revision.project_id, revision.scene_id),
        ).fetchone()
        story_position = seq_row["sequence"] if seq_row else None
        return self.insert_outbox_job(
            connection,
            project_id=revision.project_id,
            job_type="llm_wiki_ingest",
            aggregate_type="manuscript_revision",
            aggregate_id=revision.id,
            payload=manuscript_revision_index_payload(revision, previous_id, story_position),
            idempotency_key=f"llm_wiki_ingest:manuscript_revision:{revision.id}",
        )

    def get_outbox_job(self, project_id: str, job_id: str) -> OutboxJob | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, job_type, aggregate_type, aggregate_id,
                       payload_json, status, attempt_count, last_error,
                       created_at, completed_at
                FROM outbox_jobs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, job_id),
            ).fetchone()
        return outbox_job_from_row(row) if row else None

    def list_outbox_jobs(
        self,
        project_id: str,
        job_status: OutboxJobStatus | None = None,
        limit: int = 100,
    ) -> list[OutboxJob]:
        query = """
            SELECT id, project_id, job_type, aggregate_type, aggregate_id,
                   payload_json, status, attempt_count, last_error,
                   created_at, completed_at
            FROM outbox_jobs
            WHERE project_id = ?
        """
        params: list[object] = [project_id]
        if job_status is not None:
            query += " AND status = ?"
            params.append(job_status)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [outbox_job_from_row(row) for row in rows]

    def transition_outbox_job(
        self,
        project_id: str,
        job_id: str,
        *,
        job_status: OutboxJobStatus,
        error: str | None = None,
    ) -> OutboxJob | None:
        """Move a job to the given status; counts an attempt on processing."""
        now = utc_now()
        terminal = job_status in ("succeeded", "failed")
        error_text = error or ""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbox_jobs
                SET status = ?,
                    last_error = ?,
                    completed_at = ?,
                    attempt_count = attempt_count + ?
                WHERE project_id = ? AND id = ?
                """,
                (
                    job_status,
                    error_text,
                    now if terminal else "",
                    1 if job_status == "processing" else 0,
                    project_id,
                    job_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT id, project_id, job_type, aggregate_type, aggregate_id,
                       payload_json, status, attempt_count, last_error,
                       created_at, completed_at
                FROM outbox_jobs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, job_id),
            ).fetchone()
        return outbox_job_from_row(row) if row else None
