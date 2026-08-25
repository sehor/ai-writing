"""Snowflake repository: planning artifacts per project and step."""

import sqlite3

from app.models import SnowflakeArtifact


def artifact_from_row(row: sqlite3.Row) -> SnowflakeArtifact:
    return SnowflakeArtifact(
        project_id=row["project_id"],
        step_number=row["step_number"],
        artifact=row["artifact"],
        content=row["content"],
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

    def save(self, artifact: SnowflakeArtifact) -> SnowflakeArtifact:
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
