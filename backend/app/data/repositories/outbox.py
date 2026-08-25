"""Outbox repository: transactional side-effect jobs.

Jobs are always inserted inside the same transaction as the domain rows
that make them necessary (transactional outbox pattern); dispatch happens
after commit through app.outbox.service.
"""

import json
import sqlite3

from app.data.helpers import make_record_id, utc_now
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


OUTBOX_JOB_COLUMNS = """
    SELECT id, project_id, job_type, aggregate_type, aggregate_id,
           payload_json, status, attempt_count, last_error,
           created_at, completed_at
    FROM outbox_jobs
"""


class OutboxRepository:
    """SQL for the outbox_jobs table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def insert(
        self,
        *,
        project_id: str,
        job_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
        idempotency_key: str,
    ) -> str:
        """Insert a job inside the caller's transaction.

        Returns the job id. If a job with the same idempotency key already
        exists, its id is returned without inserting a duplicate.
        """
        existing = self.connection.execute(
            "SELECT id FROM outbox_jobs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            return existing["id"]
        job_id = make_record_id(
            f"outbox-{job_type}-{aggregate_id}",
            {row["id"] for row in self.connection.execute("SELECT id FROM outbox_jobs").fetchall()},
        )
        self.connection.execute(
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

    def get(self, project_id: str, job_id: str) -> OutboxJob | None:
        row = self.connection.execute(
            f"""
            {OUTBOX_JOB_COLUMNS}
            WHERE project_id = ? AND id = ?
            """,
            (project_id, job_id),
        ).fetchone()
        return outbox_job_from_row(row) if row else None

    def list_jobs(
        self,
        project_id: str,
        job_status: OutboxJobStatus | None = None,
        limit: int = 100,
    ) -> list[OutboxJob]:
        query = f"""
            {OUTBOX_JOB_COLUMNS}
            WHERE project_id = ?
        """
        params: list[object] = [project_id]
        if job_status is not None:
            query += " AND status = ?"
            params.append(job_status)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return [outbox_job_from_row(row) for row in rows]

    def transition(
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
        cursor = self.connection.execute(
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
        return self.get(project_id, job_id)
