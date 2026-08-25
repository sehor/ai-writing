"""Canon repository: confirmed story facts with optimistic concurrency."""

from __future__ import annotations

import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.models import CanonEntity, CanonEntityCreate, CanonEntityUpdate

CANON_ENTITY_COLUMNS = """
    SELECT id, project_id, entity_type, name, summary, current_state,
           constraints, last_seen, timeline_notes, version, updated_at
    FROM canon_entities
"""


class ConcurrentCanonUpdateError(RuntimeError):
    """The canon record kept changing between reads; the edit was not applied."""

    def __init__(self, project_id: str, entity_id: str):
        super().__init__(
            f"Canon entity '{entity_id}' in project '{project_id}' was modified "
            "concurrently; the update could not be applied."
        )


def canon_entity_from_row(row: sqlite3.Row) -> CanonEntity:
    return CanonEntity(
        id=row["id"],
        project_id=row["project_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        summary=row["summary"],
        current_state=row["current_state"],
        constraints=row["constraints"],
        last_seen=row["last_seen"],
        timeline_notes=row["timeline_notes"],
        version=row["version"],
        updated_at=row["updated_at"],
    )


def canon_entity_to_params(
    entity: CanonEntity,
) -> tuple[str, str, str, str, str, str, str, str, str, int, str]:
    return (
        entity.id,
        entity.project_id,
        entity.entity_type,
        entity.name,
        entity.summary,
        entity.current_state,
        entity.constraints,
        entity.last_seen,
        entity.timeline_notes,
        entity.version,
        entity.updated_at,
    )


class CanonRepository:
    """SQL for the canon_entities table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self, project_id: str) -> list[CanonEntity]:
        rows = self.connection.execute(
            f"""
            {CANON_ENTITY_COLUMNS}
            WHERE project_id = ?
            ORDER BY entity_type, name
            """,
            (project_id,),
        ).fetchall()
        return [canon_entity_from_row(row) for row in rows]

    def get(self, project_id: str, entity_id: str) -> CanonEntity | None:
        row = self.connection.execute(
            f"""
            {CANON_ENTITY_COLUMNS}
            WHERE project_id = ? AND id = ?
            """,
            (project_id, entity_id),
        ).fetchone()
        return canon_entity_from_row(row) if row else None

    def create(self, project_id: str, entity: CanonEntityCreate) -> CanonEntity:
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM canon_entities",
            ).fetchall()
        }
        created = CanonEntity(
            id=make_record_id(
                f"{project_id}-{entity.entity_type}-{entity.name}",
                existing_ids,
            ),
            project_id=project_id,
            version=1,
            updated_at=utc_now(),
            **entity.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO canon_entities (
                id, project_id, entity_type, name, summary, current_state,
                constraints, last_seen, timeline_notes, version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            canon_entity_to_params(created),
        )
        return created

    def update(self, project_id: str, entity_id: str, entity: CanonEntityUpdate):
        """Manual editor update; bumps the optimistic-concurrency version."""
        for _ in range(3):
            current = self.get(project_id, entity_id)
            if current is None:
                return None
            updated = CanonEntity(
                id=entity_id,
                project_id=project_id,
                version=current.version + 1,
                updated_at=utc_now(),
                **entity.model_dump(),
            )
            if self.apply_cas_update(updated, expected_version=current.version):
                return updated
        raise ConcurrentCanonUpdateError(project_id, entity_id)

    def apply_cas_update(self, updated: CanonEntity, *, expected_version: int) -> int:
        """Write a fully built canon row guarded by the expected version.

        Shared by editor edits (update) and accepted update write-backs.
        Returns the affected row count so callers can turn 0 into their own
        conflict error.
        """
        cursor = self.connection.execute(
            """
            UPDATE canon_entities
            SET entity_type = ?,
                name = ?,
                summary = ?,
                current_state = ?,
                constraints = ?,
                last_seen = ?,
                timeline_notes = ?,
                version = ?,
                updated_at = ?
            WHERE project_id = ? AND id = ? AND version = ?
            """,
            (
                updated.entity_type,
                updated.name,
                updated.summary,
                updated.current_state,
                updated.constraints,
                updated.last_seen,
                updated.timeline_notes,
                updated.version,
                updated.updated_at,
                updated.project_id,
                updated.id,
                expected_version,
            ),
        )
        return cursor.rowcount

    def delete(self, project_id: str, entity_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM canon_entities WHERE project_id = ? AND id = ?",
            (project_id, entity_id),
        )
        return cursor.rowcount > 0
