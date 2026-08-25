from pathlib import Path
from re import sub
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import sqlite3
from typing import Iterator, Protocol

from app.models import (
    CanonEntity,
    CanonEntityCreate,
    CanonEntityUpdate,
    MemoryRecord,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    ProjectCreate,
    ProjectSummary,
    ReferenceSuggestion,
    ReferenceSuggestionCreate,
    ReferenceSuggestionStatus,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
    SnowflakeArtifact,
    WorkflowAgentTrace,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)
from app.data.helpers import ensure_column, make_record_id, utc_now

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

class MemoryDataMixin:
    def list_memory_records(self, project_id: str) -> list[MemoryRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, record_type, title, scope, content, tags, source_ref
                FROM memory_records
                WHERE project_id = ?
                ORDER BY record_type, title
                """,
                (project_id,),
            ).fetchall()
        return [memory_record_from_row(row) for row in rows]
    def create_memory_record(
        self,
        project_id: str,
        record: MemoryRecordCreate,
        connection: sqlite3.Connection | None = None,
    ) -> MemoryRecord:
        if connection is None:
            with self.connect() as connection:
                return self.create_memory_record(project_id, record, connection)
        existing_ids = {
            row["id"]
            for row in connection.execute(
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
        connection.execute(
            """
            INSERT INTO memory_records (
                id, project_id, record_type, title, scope, content, tags, source_ref
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            memory_record_to_params(created),
        )
        return created
    def update_memory_record(
        self, project_id: str, record_id: str, record: MemoryRecordUpdate
    ) -> MemoryRecord | None:
        updated = MemoryRecord(
            id=record_id,
            project_id=project_id,
            **record.model_dump(),
        )
        with self.connect() as connection:
            cursor = connection.execute(
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
    def delete_memory_record(self, project_id: str, record_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_records WHERE project_id = ? AND id = ?",
                (project_id, record_id),
            )
        return cursor.rowcount > 0
