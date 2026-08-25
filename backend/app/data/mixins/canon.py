import sqlite3

from app.models import (
    CanonEntity,
    CanonEntityCreate,
    CanonEntityUpdate,
)
from app.data.helpers import make_record_id, utc_now

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


class CanonDataMixin:
    def list_canon_entities(self, project_id: str) -> list[CanonEntity]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                {CANON_ENTITY_COLUMNS}
                WHERE project_id = ?
                ORDER BY entity_type, name
                """,
                (project_id,),
            ).fetchall()
        return [canon_entity_from_row(row) for row in rows]

    def get_canon_entity(
        self,
        project_id: str,
        entity_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> CanonEntity | None:
        if connection is None:
            with self.connect() as owned:
                return self.get_canon_entity(project_id, entity_id, owned)
        row = connection.execute(
            f"""
            {CANON_ENTITY_COLUMNS}
            WHERE project_id = ? AND id = ?
            """,
            (project_id, entity_id),
        ).fetchone()
        return canon_entity_from_row(row) if row else None

    def create_canon_entity(
        self,
        project_id: str,
        entity: CanonEntityCreate,
        connection: sqlite3.Connection | None = None,
    ) -> CanonEntity:
        if connection is None:
            with self.connect() as connection:
                return self.create_canon_entity(project_id, entity, connection)
        existing_ids = {
            row["id"]
            for row in connection.execute(
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
        connection.execute(
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

    def update_canon_entity(
        self, project_id: str, entity_id: str, entity: CanonEntityUpdate
    ) -> CanonEntity | None:
        """Manual editor update; bumps the optimistic-concurrency version."""
        with self.connect() as connection:
            for _ in range(3):
                current = self.get_canon_entity(project_id, entity_id, connection)
                if current is None:
                    return None
                updated = CanonEntity(
                    id=entity_id,
                    project_id=project_id,
                    version=current.version + 1,
                    updated_at=utc_now(),
                    **entity.model_dump(),
                )
                cursor = connection.execute(
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
                        project_id,
                        entity_id,
                        current.version,
                    ),
                )
                if cursor.rowcount:
                    return updated
            raise ConcurrentCanonUpdateError(project_id, entity_id)

    def delete_canon_entity(self, project_id: str, entity_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM canon_entities WHERE project_id = ? AND id = ?",
                (project_id, entity_id),
            )
        return cursor.rowcount > 0
