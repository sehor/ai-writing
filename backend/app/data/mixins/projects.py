from contextlib import contextmanager
import sqlite3
from typing import Iterator

from app.models import (
    ProjectCreate,
    ProjectSummary,
)
from app.data.helpers import ensure_column, make_record_id


def make_project_id(title: str, existing_ids: set[str]) -> str:
    return make_record_id(title, existing_ids)


def project_from_row(row: sqlite3.Row) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"],
        title=row["title"],
        premise=row["premise"],
        current_step=row["current_step"],
    )


class ProjectsDataMixin:
    def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    premise TEXT NOT NULL,
                    current_step INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snowflake_artifacts (
                    project_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    artifact TEXT NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY (project_id, step_number),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS canon_entities (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    current_state TEXT NOT NULL,
                    constraints TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    timeline_notes TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT '',
                    UNIQUE (project_id, entity_type, name),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS scene_contracts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    chapter_id TEXT NOT NULL DEFAULT '',
                    sequence INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    pov TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    conflict TEXT NOT NULL,
                    turning_point TEXT NOT NULL,
                    required_canon TEXT NOT NULL,
                    forbidden_facts TEXT NOT NULL,
                    open_threads TEXT NOT NULL,
                    source_artifact_step INTEGER NOT NULL,
                    UNIQUE (project_id, sequence),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS manuscript_chapters (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    UNIQUE (project_id, sequence),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS manuscript_proposals (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    context TEXT NOT NULL,
                    checklist_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS manuscript_scenes (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    accepted_at TEXT NOT NULL,
                    UNIQUE (project_id, scene_id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (proposal_id) REFERENCES manuscript_proposals(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS manuscript_revisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (project_id, scene_id, version),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (proposal_id) REFERENCES manuscript_proposals(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS writeback_proposals (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    action TEXT NOT NULL,
                    title TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    target_record_id TEXT NOT NULL DEFAULT '',
                    expected_version INTEGER,
                    changes_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    applied_record_id TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reference_suggestions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    suggestion_type TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_ref TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    used_context TEXT NOT NULL,
                    canon_warnings_json TEXT NOT NULL,
                    style_notes_json TEXT NOT NULL,
                    graph_warnings_json TEXT NOT NULL,
                    proposed_writebacks_json TEXT NOT NULL,
                    workflow_trace_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_memory_records_project_id ON memory_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_manuscript_proposals_project_id_scene_id ON manuscript_proposals(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_writeback_proposals_project_id ON writeback_proposals(project_id);
                CREATE INDEX IF NOT EXISTS idx_reference_suggestions_project_id ON reference_suggestions(project_id);

                CREATE TABLE IF NOT EXISTS outbox_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_jobs_project_id_status ON outbox_jobs(project_id, status);

                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    processor TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    run_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    UNIQUE (project_id, source_ref, processor, input_hash),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_analysis_runs_project_id ON analysis_runs(project_id);
                """
            )
            ensure_column(
                connection,
                "scene_contracts",
                "chapter_id",
                "TEXT NOT NULL DEFAULT ''",
            )
            # Phase 3 (P1-02): optimistic-concurrency columns for Canon so
            # update write-backs can detect records changed after proposal
            # creation. Existing rows keep working as version 1.
            ensure_column(
                connection,
                "canon_entities",
                "version",
                "INTEGER NOT NULL DEFAULT 1",
            )
            ensure_column(
                connection,
                "canon_entities",
                "updated_at",
                "TEXT NOT NULL DEFAULT ''",
            )
            # Phase 3 (P1-02): update write-backs carry an optimistic
            # concurrency handle and field-level changes.
            ensure_column(
                connection,
                "writeback_proposals",
                "target_record_id",
                "TEXT NOT NULL DEFAULT ''",
            )
            ensure_column(
                connection,
                "writeback_proposals",
                "expected_version",
                "INTEGER",
            )
            ensure_column(
                connection,
                "writeback_proposals",
                "changes_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            if not connection.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
                connection.execute(
                    """
                    INSERT INTO projects (id, title, premise, current_step)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        "demo-novel",
                        "Demo Novel",
                        "A prototype project for Snowflake-driven AI long-form writing.",
                        1,
                    ),
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def list_projects(self) -> list[ProjectSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, premise, current_step
                FROM projects
                ORDER BY rowid
                """
            ).fetchall()
        return [project_from_row(row) for row in rows]

    def create_project(self, project: ProjectCreate) -> ProjectSummary:
        with self.connect() as connection:
            existing_ids = {
                row["id"] for row in connection.execute("SELECT id FROM projects").fetchall()
            }
            created = ProjectSummary(
                id=make_project_id(project.title, existing_ids),
                title=project.title,
                premise=project.premise,
                current_step=1,
            )
            connection.execute(
                """
                INSERT INTO projects (id, title, premise, current_step)
                VALUES (?, ?, ?, ?)
                """,
                (
                    created.id,
                    created.title,
                    created.premise,
                    created.current_step,
                ),
            )
        return created

    def get_project(self, project_id: str) -> ProjectSummary | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, premise, current_step
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        return project_from_row(row) if row else None

    def project_exists(self, project_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ? LIMIT 1",
                (project_id,),
            ).fetchone()
        return row is not None

    def advance_project_current_step(
        self,
        project_id: str,
        completed_step: int,
        connection: sqlite3.Connection | None = None,
    ) -> ProjectSummary | None:
        next_step = min(completed_step + 1, 10)
        if connection is None:
            with self.connect() as owned:
                return self.advance_project_current_step(project_id, completed_step, owned)
        connection.execute(
            """
            UPDATE projects
            SET current_step = MAX(current_step, ?)
            WHERE id = ?
            """,
            (next_step, project_id),
        )
        row = connection.execute(
            "SELECT id, title, premise, current_step FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return project_from_row(row) if row else None
