"""Outbox repository: transactional side-effect jobs.

Jobs are always inserted inside the same transaction as the domain rows
that make them necessary (transactional outbox pattern); dispatch happens
after commit through app.outbox.service.

Every status change is a compare-and-set on the current status so two
dispatchers can never both win one job (P1-02).
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
        processing_started_at=row["processing_started_at"],
    )


OUTBOX_JOB_COLUMNS = """
    SELECT id, project_id, job_type, aggregate_type, aggregate_id,
           payload_json, status, attempt_count, last_error,
           created_at, completed_at, processing_started_at
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
        aggregate_type: str | None = None,
    ) -> list[OutboxJob]:
        query = f"""
            {OUTBOX_JOB_COLUMNS}
            WHERE project_id = ?
        """
        params: list[object] = [project_id]
        if job_status is not None:
            query += " AND status = ?"
            params.append(job_status)
        if aggregate_type is not None:
            query += " AND aggregate_type = ?"
            params.append(aggregate_type)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return [outbox_job_from_row(row) for row in rows]

    def pending_project_ids(self) -> list[str]:
        """Projects that still hold at least one pending job."""
        rows = self.connection.execute(
            "SELECT DISTINCT project_id FROM outbox_jobs WHERE status = 'pending'"
            " ORDER BY project_id"
        ).fetchall()
        return [row["project_id"] for row in rows]

    def claim(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Atomically claim a pending job for execution.

        The compare-and-set makes the claim single-winner: only a caller
        whose UPDATE moved the row from 'pending' may run the handler.
        """
        cursor = self.connection.execute(
            """
            UPDATE outbox_jobs
            SET status = 'processing',
                attempt_count = attempt_count + 1,
                processing_started_at = ?,
                completed_at = '',
                last_error = ''
            WHERE project_id = ? AND id = ? AND status = 'pending'
            """,
            (utc_now(), project_id, job_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.get(project_id, job_id)

    def complete(
        self,
        project_id: str,
        job_id: str,
        *,
        succeeded: bool,
        error: str | None = None,
    ) -> OutboxJob | None:
        """Finalize a claimed job; only valid from 'processing'."""
        cursor = self.connection.execute(
            """
            UPDATE outbox_jobs
            SET status = ?,
                last_error = ?,
                completed_at = ?,
                processing_started_at = ''
            WHERE project_id = ? AND id = ? AND status = 'processing'
            """,
            (
                "succeeded" if succeeded else "failed",
                error or "",
                utc_now(),
                project_id,
                job_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return self.get(project_id, job_id)

    def reset_failed(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Retry gate: move a failed job back to pending via CAS.

        A concurrent retry loses here instead of running the handler twice.
        """
        cursor = self.connection.execute(
            """
            UPDATE outbox_jobs
            SET status = 'pending',
                last_error = '',
                completed_at = '',
                processing_started_at = ''
            WHERE project_id = ? AND id = ? AND status = 'failed'
            """,
            (project_id, job_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.get(project_id, job_id)

    def recover_stale(self, cutoff: str) -> list[OutboxJob]:
        """Reset processing jobs whose lease expired before the cutoff.

        Rows stamped empty predate lease tracking and are treated as stale;
        jobs claimed by current code always carry a stamp in the same
        statement that sets 'processing'.
        """
        rows = self.connection.execute(
            "SELECT project_id, id FROM outbox_jobs"
            " WHERE status = 'processing'"
            " AND (processing_started_at = '' OR processing_started_at < ?)",
            (cutoff,),
        ).fetchall()
        recovered: list[OutboxJob] = []
        for row in rows:
            cursor = self.connection.execute(
                "UPDATE outbox_jobs SET status = 'pending', processing_started_at = ''"
                " WHERE project_id = ? AND id = ? AND status = 'processing'",
                (row["project_id"], row["id"]),
            )
            if cursor.rowcount == 1:
                job = self.get(row["project_id"], row["id"])
                if job is not None:
                    recovered.append(job)
        return recovered
