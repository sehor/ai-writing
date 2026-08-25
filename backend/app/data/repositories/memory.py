"""Memory repository: continuity/style records (not fact correctness)."""

from __future__ import annotations

import sqlite3

from app.data.helpers import make_record_id
from app.models import MemoryRecord, MemoryRecordCreate, MemoryRecordUpdate


def memory_record_from_row(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        project_id=row["project_id"],
        record_type=row["record_type"],
        title=row["title"],
        scope=row["scope"],
        content=row["content"],
        tags=row["tags"],
        source_ref=row["source_ref"],
    )


def memory_record_to_params(
    record: MemoryRecord,
) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        record.id,
        record.project_id,
        record.record_type,
        record.title,
        record.scope,
        record.content,
        record.tags,
        record.source_ref,
    )


class MemoryRepository:
    """SQL for the memory_records table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self, project_id: str) -> list[MemoryRecord]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, record_type, title, scope, content, tags, source_ref
            FROM memory_records
            WHERE project_id = ?
            ORDER BY record_type, title
            """,
            (project_id,),
        ).fetchall()
        return [memory_record_from_row(row) for row in rows]

    def create(self, project_id: str, record: MemoryRecordCreate) -> MemoryRecord:
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM memory_records",
            ).fetchall()
        }
        created = MemoryRecord(
            id=make_record_id(
                f"{project_id}-{record.record_type}-{record.title}",
                existing_ids,
            ),
            project_id=project_id,
            **record.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO memory_records (
                id, project_id, record_type, title, scope, content, tags, source_ref
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            memory_record_to_params(created),
        )
        return created

    def update(self, project_id: str, record_id: str, record: MemoryRecordUpdate):
        updated = MemoryRecord(
            id=record_id,
            project_id=project_id,
            **record.model_dump(),
        )
        cursor = self.connection.execute(
            """
            UPDATE memory_records
            SET record_type = ?,
                title = ?,
                scope = ?,
                content = ?,
                tags = ?,
                source_ref = ?
            WHERE project_id = ? AND id = ?
            """,
            (
                updated.record_type,
                updated.title,
                updated.scope,
                updated.content,
                updated.tags,
                updated.source_ref,
                project_id,
                record_id,
            ),
        )
        return updated if cursor.rowcount else None

    def delete(self, project_id: str, record_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM memory_records WHERE project_id = ? AND id = ?",
            (project_id, record_id),
        )
        return cursor.rowcount > 0
