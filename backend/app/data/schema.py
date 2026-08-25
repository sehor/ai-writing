"""SQLite schema creation and column migrations.

Lifted verbatim out of the former ProjectsDataMixin.init() when the store
was split into repositories (P2-03): same tables, indexes, ensure_column
migrations and demo-novel seed, now applied through initialize_schema()
against a caller-supplied connection.
"""

import sqlite3

from app.data.helpers import ensure_column

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS scene_proposals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    chapter_id TEXT NOT NULL DEFAULT '',
    chapter_hint TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    pov TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL DEFAULT '',
    conflict TEXT NOT NULL DEFAULT '',
    turning_point TEXT NOT NULL DEFAULT '',
    required_canon_ids TEXT NOT NULL DEFAULT '',
    required_canon_raw TEXT NOT NULL DEFAULT '',
    forbidden_fact_refs TEXT NOT NULL DEFAULT '',
    open_threads TEXT NOT NULL DEFAULT '',
    source_ref TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    applied_scene_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_scene_proposals_project_id ON scene_proposals(project_id);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create every table/index and run the additive column migrations.

    Idempotent: safe to call on an existing database (all statements are
    IF NOT EXISTS / add-column-if-missing).
    """
    connection.executescript(SCHEMA_SQL)
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
