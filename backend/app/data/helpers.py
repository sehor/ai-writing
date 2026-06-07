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

def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    import re
    if not re.match(r"^[A-Za-z0-9_]+$", table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    if not re.match(r"^[A-Za-z0-9_]+$", column_name):
        raise ValueError(f"Invalid column name: {column_name}")
        
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )

def make_record_id(title: str, existing_ids: set[str]) -> str:
    base = sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "project"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate

def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
