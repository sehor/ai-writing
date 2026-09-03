"""Snowflake repository: accepted projection plus append-only revision history."""

import json
import sqlite3
from uuid import uuid4

from app.data.helpers import utc_now
from app.models import (
    SnowflakeArtifact,
    SnowflakeArtifactHead,
    SnowflakeArtifactRevision,
    SnowflakeArtifactRevisionCreate,
    SnowflakeRevisionSource,
    SnowflakeRevisionStatus,
)
from app.snowflake.dependencies import upstream_snapshot
from app.snowflake.step_spec import SNOWFLAKE_STEP_SPECS, get_step_spec


def artifact_from_row(row: sqlite3.Row) -> SnowflakeArtifact:
    return SnowflakeArtifact(
        project_id=row["project_id"],
        step_number=row["step_number"],
        artifact=row["artifact"],
        content=row["content"],
    )


def _json_object(value: str) -> dict:
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}


def revision_from_row(row: sqlite3.Row) -> SnowflakeArtifactRevision:
    return SnowflakeArtifactRevision(
        id=row["id"],
        project_id=row["project_id"],
        step_number=row["step_number"],
        artifact_type=row["artifact_type"],
        revision_no=row["revision_no"],
        source=row["source"],
        status=row["status"],
        content=row["content"],
        structured_payload=_json_object(row["structured_payload"]),
        schema_version=row["schema_version"],
        parent_revision_id=row["parent_revision_id"],
        base_head_revision_id=row["base_head_revision_id"],
        upstream_snapshot=_json_object(row["upstream_snapshot"]),
        review_reason=row["review_reason"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


def head_from_row(row: sqlite3.Row) -> SnowflakeArtifactHead:
    return SnowflakeArtifactHead(
        project_id=row["project_id"],
        step_number=row["step_number"],
        accepted_revision_id=row["accepted_revision_id"],
        state=row["state"],
        stale_reason=row["stale_reason"],
        stale_trigger_revision_id=row["stale_trigger_revision_id"],
    )


class SnowflakeRepository:
    """SQL for the snowflake_artifacts table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list_by_project(self, project_id: str) -> list[SnowflakeArtifact]:
        rows = self.connection.execute(
            """
            SELECT project_id, step_number, artifact, content
            FROM snowflake_artifacts
            WHERE project_id = ?
            ORDER BY step_number
            """,
            (project_id,),
        ).fetchall()
        return [artifact_from_row(row) for row in rows]

    def get(self, project_id: str, step_number: int) -> SnowflakeArtifact | None:
        row = self.connection.execute(
            """
            SELECT project_id, step_number, artifact, content
            FROM snowflake_artifacts
            WHERE project_id = ? AND step_number = ?
            """,
            (project_id, step_number),
        ).fetchone()
        return artifact_from_row(row) if row else None

    def update_accepted_projection(self, artifact: SnowflakeArtifact) -> SnowflakeArtifact:
        """Update the legacy accepted-head projection only."""
        self.connection.execute(
            """
            INSERT INTO snowflake_artifacts (project_id, step_number, artifact, content)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, step_number) DO UPDATE SET
                artifact = excluded.artifact,
                content = excluded.content
            """,
            (
                artifact.project_id,
                artifact.step_number,
                artifact.artifact,
                artifact.content,
            ),
        )
        return artifact

    def accepted_head_ids(self, project_id: str) -> dict[int, str]:
        rows = self.connection.execute(
            """
            SELECT step_number, accepted_revision_id
            FROM snowflake_artifact_heads
            WHERE project_id = ? AND accepted_revision_id <> ''
            """,
            (project_id,),
        ).fetchall()
        return {int(row["step_number"]): row["accepted_revision_id"] for row in rows}

    def get_head(self, project_id: str, step_number: int) -> SnowflakeArtifactHead:
        row = self.connection.execute(
            """
            SELECT project_id, step_number, accepted_revision_id, state,
                   stale_reason, stale_trigger_revision_id
            FROM snowflake_artifact_heads
            WHERE project_id = ? AND step_number = ?
            """,
            (project_id, step_number),
        ).fetchone()
        if row:
            return head_from_row(row)
        return SnowflakeArtifactHead(project_id=project_id, step_number=step_number)

    def list_heads(self, project_id: str) -> list[SnowflakeArtifactHead]:
        return [self.get_head(project_id, spec.number) for spec in SNOWFLAKE_STEP_SPECS]

    def get_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeArtifactRevision | None:
        row = self.connection.execute(
            """
            SELECT * FROM snowflake_artifact_revisions
            WHERE project_id = ? AND id = ?
            """,
            (project_id, revision_id),
        ).fetchone()
        return revision_from_row(row) if row else None

    def list_revisions(
        self,
        project_id: str,
        step_number: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[SnowflakeArtifactRevision], int]:
        total = int(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM snowflake_artifact_revisions
                WHERE project_id = ? AND step_number = ?
                """,
                (project_id, step_number),
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            """
            SELECT * FROM snowflake_artifact_revisions
            WHERE project_id = ? AND step_number = ?
            ORDER BY revision_no DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, step_number, limit, offset),
        ).fetchall()
        return [revision_from_row(row) for row in rows], total

    def pending_counts(self, project_id: str) -> dict[int, int]:
        rows = self.connection.execute(
            """
            SELECT step_number, COUNT(*) AS total
            FROM snowflake_artifact_revisions
            WHERE project_id = ? AND status IN ('draft', 'pending_review')
            GROUP BY step_number
            """,
            (project_id,),
        ).fetchall()
        return {int(row["step_number"]): int(row["total"]) for row in rows}

    def create_revision(
        self,
        project_id: str,
        create: SnowflakeArtifactRevisionCreate,
        *,
        status: SnowflakeRevisionStatus | None = None,
        source: SnowflakeRevisionSource | None = None,
    ) -> SnowflakeArtifactRevision:
        spec = get_step_spec(create.step_number)
        if spec.virtual:
            raise ValueError("Snowflake step 10 is a virtual Manuscript milestone.")
        revision_no = int(
            self.connection.execute(
                """
                SELECT COALESCE(MAX(revision_no), 0) + 1
                FROM snowflake_artifact_revisions
                WHERE project_id = ? AND step_number = ?
                """,
                (project_id, create.step_number),
            ).fetchone()[0]
        )
        actual_source = source or create.source
        actual_status = status or ("pending_review" if actual_source == "ai" else "draft")
        head = self.get_head(project_id, create.step_number)
        revision_id = f"snowflake:{project_id}:{create.step_number}:{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO snowflake_artifact_revisions (
                id, project_id, step_number, artifact_type, revision_no,
                source, status, content, structured_payload, schema_version,
                parent_revision_id, base_head_revision_id, upstream_snapshot,
                created_at, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (
                revision_id,
                project_id,
                create.step_number,
                spec.artifact_type,
                revision_no,
                actual_source,
                actual_status,
                create.content,
                json.dumps(create.structured_payload, ensure_ascii=False),
                create.schema_version,
                create.parent_revision_id,
                create.base_head_revision_id or head.accepted_revision_id,
                json.dumps(
                    upstream_snapshot(create.step_number, self.accepted_head_ids(project_id)),
                    ensure_ascii=False,
                ),
                utc_now(),
            ),
        )
        created = self.get_revision(project_id, revision_id)
        if created is None:
            raise RuntimeError("Snowflake revision insert did not produce a readable record.")
        return created

    def patch_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        content: str | None,
        structured_payload: dict | None,
    ) -> SnowflakeArtifactRevision | None:
        current = self.get_revision(project_id, revision_id)
        if current is None:
            return None
        if current.status not in {"draft", "pending_review"}:
            raise ValueError("Only draft or pending Snowflake revisions can be edited.")
        self.connection.execute(
            """
            UPDATE snowflake_artifact_revisions
            SET content = ?, structured_payload = ?
            WHERE project_id = ? AND id = ?
            """,
            (
                content if content is not None else current.content,
                json.dumps(
                    structured_payload
                    if structured_payload is not None
                    else current.structured_payload,
                    ensure_ascii=False,
                ),
                project_id,
                revision_id,
            ),
        )
        return self.get_revision(project_id, revision_id)

    def set_revision_status(
        self,
        project_id: str,
        revision_id: str,
        status: SnowflakeRevisionStatus,
        *,
        review_reason: str = "",
    ) -> SnowflakeArtifactRevision:
        self.connection.execute(
            """
            UPDATE snowflake_artifact_revisions
            SET status = ?, review_reason = ?, reviewed_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (status, review_reason, utc_now(), project_id, revision_id),
        )
        revision = self.get_revision(project_id, revision_id)
        if revision is None:
            raise LookupError("Snowflake revision not found.")
        return revision

    def accept_revision(self, revision: SnowflakeArtifactRevision) -> SnowflakeArtifactHead:
        current = self.get_head(revision.project_id, revision.step_number)
        if current.accepted_revision_id and current.accepted_revision_id != revision.id:
            self.connection.execute(
                """
                UPDATE snowflake_artifact_revisions
                SET status = 'superseded'
                WHERE project_id = ? AND id = ? AND status = 'accepted'
                """,
                (revision.project_id, current.accepted_revision_id),
            )
        self.connection.execute(
            """
            INSERT INTO snowflake_artifact_heads (
                project_id, step_number, accepted_revision_id, state,
                stale_reason, stale_trigger_revision_id
            ) VALUES (?, ?, ?, 'approved', '', '')
            ON CONFLICT(project_id, step_number) DO UPDATE SET
                accepted_revision_id = excluded.accepted_revision_id,
                state = 'approved',
                stale_reason = '',
                stale_trigger_revision_id = ''
            """,
            (revision.project_id, revision.step_number, revision.id),
        )
        return self.get_head(revision.project_id, revision.step_number)

    def mark_stale(
        self,
        project_id: str,
        step_numbers: tuple[int, ...],
        *,
        reason: str,
        trigger_revision_id: str,
    ) -> None:
        for step_number in step_numbers:
            current = self.get_head(project_id, step_number)
            if current.state == "missing" and step_number != 10:
                continue
            self.connection.execute(
                """
                INSERT INTO snowflake_artifact_heads (
                    project_id, step_number, accepted_revision_id, state,
                    stale_reason, stale_trigger_revision_id
                ) VALUES (?, ?, ?, 'stale', ?, ?)
                ON CONFLICT(project_id, step_number) DO UPDATE SET
                    state = 'stale',
                    stale_reason = excluded.stale_reason,
                    stale_trigger_revision_id = excluded.stale_trigger_revision_id
                """,
                (
                    project_id,
                    step_number,
                    current.accepted_revision_id,
                    reason,
                    trigger_revision_id,
                ),
            )

    def skip_step(self, project_id: str, step_number: int) -> SnowflakeArtifactHead:
        if not get_step_spec(step_number).optional:
            raise ValueError("Only optional Snowflake steps can be skipped.")
        self.connection.execute(
            """
            INSERT INTO snowflake_artifact_heads (
                project_id, step_number, accepted_revision_id, state,
                stale_reason, stale_trigger_revision_id
            ) VALUES (?, ?, '', 'skipped', '', '')
            ON CONFLICT(project_id, step_number) DO UPDATE SET
                accepted_revision_id = '', state = 'skipped',
                stale_reason = '', stale_trigger_revision_id = ''
            """,
            (project_id, step_number),
        )
        return self.get_head(project_id, step_number)
