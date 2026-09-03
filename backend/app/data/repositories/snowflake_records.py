"""Pageable, append-only records for Snowflake steps 6–9."""

import json
import sqlite3
from uuid import uuid4

from app.data.helpers import utc_now
from app.models import (
    SnowflakeRecordHead,
    SnowflakeRecordRevision,
    SnowflakeRecordRevisionCreate,
    SnowflakeRevisionStatus,
)


def record_revision_from_row(row: sqlite3.Row) -> SnowflakeRecordRevision:
    payload = json.loads(row["payload_json"] or "{}")
    return SnowflakeRecordRevision(
        id=row["id"],
        project_id=row["project_id"],
        step_number=row["step_number"],
        record_id=row["record_id"],
        position=row["position"],
        revision_no=row["revision_no"],
        source=row["source"],
        status=row["status"],
        payload=payload if isinstance(payload, dict) else {},
        base_revision_id=row["base_revision_id"],
        review_reason=row["review_reason"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


def record_head_from_row(row: sqlite3.Row) -> SnowflakeRecordHead:
    return SnowflakeRecordHead(
        project_id=row["project_id"],
        step_number=row["step_number"],
        record_id=row["record_id"],
        accepted_revision_id=row["accepted_revision_id"],
        state=row["state"],
    )


class SnowflakeRecordRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        project_id: str,
        create: SnowflakeRecordRevisionCreate,
        *,
        status: SnowflakeRevisionStatus = "draft",
    ) -> SnowflakeRecordRevision:
        head = self.get_head(project_id, create.step_number, create.record_id)
        expected = create.base_revision_id
        actual = head.accepted_revision_id if head else ""
        if expected != actual:
            raise ValueError("The Snowflake record changed; reload before creating a revision.")
        revision_no = int(
            self.connection.execute(
                """
                SELECT COALESCE(MAX(revision_no), 0) + 1
                FROM snowflake_record_revisions
                WHERE project_id = ? AND step_number = ? AND record_id = ?
                """,
                (project_id, create.step_number, create.record_id),
            ).fetchone()[0]
        )
        revision_id = f"snowflake-record:{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO snowflake_record_revisions (
                id, project_id, step_number, record_id, position, revision_no,
                source, status, payload_json, base_revision_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                project_id,
                create.step_number,
                create.record_id,
                create.position,
                revision_no,
                create.source,
                status,
                json.dumps(create.payload, ensure_ascii=False),
                create.base_revision_id,
                utc_now(),
            ),
        )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO snowflake_record_heads (
                project_id, step_number, record_id, accepted_revision_id, state
            ) VALUES (?, ?, ?, '', ?)
            """,
            (project_id, create.step_number, create.record_id, status),
        )
        return self.get_revision(project_id, revision_id)  # type: ignore[return-value]

    def get_revision(self, project_id: str, revision_id: str) -> SnowflakeRecordRevision | None:
        row = self.connection.execute(
            "SELECT * FROM snowflake_record_revisions WHERE project_id = ? AND id = ?",
            (project_id, revision_id),
        ).fetchone()
        return record_revision_from_row(row) if row else None

    def get_head(self, project_id: str, step_number: int, record_id: str) -> SnowflakeRecordHead | None:
        row = self.connection.execute(
            """
            SELECT * FROM snowflake_record_heads
            WHERE project_id = ? AND step_number = ? AND record_id = ?
            """,
            (project_id, step_number, record_id),
        ).fetchone()
        return record_head_from_row(row) if row else None

    def list_current(
        self, project_id: str, step_number: int, *, limit: int, offset: int
    ) -> tuple[list[SnowflakeRecordRevision], int]:
        total = int(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM snowflake_record_heads
                WHERE project_id = ? AND step_number = ?
                """,
                (project_id, step_number),
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            """
            SELECT r.*
            FROM snowflake_record_heads h
            JOIN snowflake_record_revisions r ON r.id = (
                SELECT r2.id FROM snowflake_record_revisions r2
                WHERE r2.project_id = h.project_id
                  AND r2.step_number = h.step_number
                  AND r2.record_id = h.record_id
                ORDER BY r2.revision_no DESC LIMIT 1
            )
            WHERE h.project_id = ? AND h.step_number = ?
            ORDER BY r.position, r.record_id
            LIMIT ? OFFSET ?
            """,
            (project_id, step_number, limit, offset),
        ).fetchall()
        return [record_revision_from_row(row) for row in rows], total

    def get_current_by_record_ids(
        self,
        project_id: str,
        step_number: int,
        record_ids: list[str],
    ) -> list[SnowflakeRecordRevision]:
        if not record_ids:
            return []
        placeholders = ", ".join("?" for _ in record_ids)
        rows = self.connection.execute(
            f"""
            SELECT r.*
            FROM snowflake_record_heads h
            JOIN snowflake_record_revisions r ON r.id = (
                SELECT r2.id FROM snowflake_record_revisions r2
                WHERE r2.project_id = h.project_id
                  AND r2.step_number = h.step_number
                  AND r2.record_id = h.record_id
                ORDER BY r2.revision_no DESC LIMIT 1
            )
            WHERE h.project_id = ? AND h.step_number = ?
              AND h.record_id IN ({placeholders})
            """,
            (project_id, step_number, *record_ids),
        ).fetchall()
        by_id = {row["record_id"]: record_revision_from_row(row) for row in rows}
        return [by_id[record_id] for record_id in record_ids if record_id in by_id]

    def list_history(
        self,
        project_id: str,
        step_number: int,
        record_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[SnowflakeRecordRevision], int]:
        total = int(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM snowflake_record_revisions
                WHERE project_id = ? AND step_number = ? AND record_id = ?
                """,
                (project_id, step_number, record_id),
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            """
            SELECT * FROM snowflake_record_revisions
            WHERE project_id = ? AND step_number = ? AND record_id = ?
            ORDER BY revision_no DESC LIMIT ? OFFSET ?
            """,
            (project_id, step_number, record_id, limit, offset),
        ).fetchall()
        return [record_revision_from_row(row) for row in rows], total

    def decide(
        self,
        project_id: str,
        revision_id: str,
        *,
        decision: str,
        expected_revision_id: str,
        review_reason: str,
    ) -> tuple[SnowflakeRecordRevision, SnowflakeRecordHead]:
        revision = self.get_revision(project_id, revision_id)
        if revision is None:
            raise LookupError("Snowflake record revision not found.")
        if revision.status not in {"draft", "pending_review"}:
            raise ValueError("Snowflake record revision is already reviewed.")
        head = self.get_head(project_id, revision.step_number, revision.record_id)
        actual = head.accepted_revision_id if head else ""
        if actual != expected_revision_id or revision.base_revision_id != expected_revision_id:
            raise ValueError("The accepted Snowflake record changed; reload before deciding.")
        now = utc_now()
        status = "accepted" if decision == "accepted" else "rejected"
        self.connection.execute(
            """
            UPDATE snowflake_record_revisions
            SET status = ?, review_reason = ?, reviewed_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (status, review_reason, now, project_id, revision_id),
        )
        if decision == "accepted":
            if actual:
                self.connection.execute(
                    """
                    UPDATE snowflake_record_revisions SET status = 'superseded'
                    WHERE project_id = ? AND id = ? AND status = 'accepted'
                    """,
                    (project_id, actual),
                )
            self.connection.execute(
                """
                UPDATE snowflake_record_heads
                SET accepted_revision_id = ?, state = 'approved'
                WHERE project_id = ? AND step_number = ? AND record_id = ?
                """,
                (revision_id, project_id, revision.step_number, revision.record_id),
            )
        resolved = self.get_revision(project_id, revision_id)
        resolved_head = self.get_head(project_id, revision.step_number, revision.record_id)
        assert resolved is not None and resolved_head is not None
        return resolved, resolved_head
