"""Versioned, transactional SQLite schema migrations.

P2-06 replaces the old apply-everything-every-time bootstrap with an ordered
migration list recorded in a ``schema_migrations`` table:

- every migration has a positive integer version and a unique name;
- startup reads the applied versions and runs each pending migration in order,
  inside exactly one transaction together with its ``schema_migrations`` row —
  a failure rolls the migration back and stops startup with an error naming it;
- migrations stay idempotent (``IF NOT EXISTS`` / add-column-if-missing) so a
database created by any earlier era converges to the same final shape.

Version 1 is today's full DDL baseline; later versions mirror the additive
column changes that previously ran unconditionally through ``ensure_column``.
New schema changes append a new migration and must never edit old ones.
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from app.data.helpers import ensure_column, utc_now
from app.snowflake.dependencies import upstream_snapshot

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


@dataclass(frozen=True)
class Migration:
    """One ordered schema change: ``version`` is permanent once released."""

    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def _apply_baseline_schema(connection: sqlite3.Connection) -> None:
    _run_script(connection, SCHEMA_SQL)


def _add_scene_contracts_chapter_id(connection: sqlite3.Connection) -> None:
    ensure_column(connection, "scene_contracts", "chapter_id", "TEXT NOT NULL DEFAULT ''")


def _add_canon_version_tracking(connection: sqlite3.Connection) -> None:
    # P1-02: optimistic-concurrency columns for Canon so update write-backs
    # can detect records changed after proposal creation. Existing rows keep
    # working as version 1.
    ensure_column(connection, "canon_entities", "version", "INTEGER NOT NULL DEFAULT 1")
    ensure_column(connection, "canon_entities", "updated_at", "TEXT NOT NULL DEFAULT ''")


def _add_writeback_optimistic_concurrency(connection: sqlite3.Connection) -> None:
    # P1-02: update write-backs carry an optimistic concurrency handle and
    # field-level changes.
    ensure_column(connection, "writeback_proposals", "target_record_id", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "writeback_proposals", "expected_version", "INTEGER")
    ensure_column(connection, "writeback_proposals", "changes_json", "TEXT NOT NULL DEFAULT '{}'")


def _add_outbox_processing_lease(connection: sqlite3.Connection) -> None:
    # P1-02: atomic outbox claiming stamps when a job moved to 'processing'
    # so a crashed dispatcher's lease can be detected and recovered.
    ensure_column(connection, "outbox_jobs", "processing_started_at", "TEXT NOT NULL DEFAULT ''")


def _add_narrative_state_tables(connection: sqlite3.Connection) -> None:
    _run_script(
        connection,
        """
        CREATE TABLE IF NOT EXISTS story_facts (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            value TEXT NOT NULL,
            valid_from_scene INTEGER NOT NULL,
            valid_to_scene INTEGER,
            reader_visible_from INTEGER,
            source_ref TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmed',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_story_facts_project_interval
            ON story_facts(project_id, valid_from_scene, valid_to_scene);
        CREATE TABLE IF NOT EXISTS story_fact_character_knowledge (
            project_id TEXT NOT NULL,
            fact_id TEXT NOT NULL,
            character TEXT NOT NULL,
            known_from_scene INTEGER NOT NULL,
            PRIMARY KEY (project_id, fact_id, character),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (fact_id) REFERENCES story_facts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS story_threads (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            thread_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            planted_at INTEGER,
            target_payoff_from INTEGER,
            target_payoff_to INTEGER,
            importance INTEGER NOT NULL DEFAULT 3,
            reveal_constraints TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_story_threads_project_status
            ON story_threads(project_id, status);
        CREATE TABLE IF NOT EXISTS story_thread_events (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            scene_id TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (thread_id) REFERENCES story_threads(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scene_contracts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_story_thread_events_thread
            ON story_thread_events(project_id, thread_id);
        """,
    )


def _add_narrative_domain_phase0_tables(connection: sqlite3.Connection) -> None:
    _run_script(
        connection,
        """
        CREATE TABLE IF NOT EXISTS knowledge_states (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            fact_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            character TEXT NOT NULL COLLATE NOCASE DEFAULT '',
            known_from_scene INTEGER NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmed',
            UNIQUE (project_id, fact_id, scope, character),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (fact_id) REFERENCES story_facts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_states_lookup
            ON knowledge_states(project_id, scope, character, known_from_scene);
        CREATE TABLE IF NOT EXISTS narrative_relations (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            relation TEXT NOT NULL,
            valid_from INTEGER NOT NULL,
            valid_to INTEGER,
            confidence REAL NOT NULL DEFAULT 1.0,
            source_ref TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmed',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_narrative_relations_project_interval
            ON narrative_relations(project_id, valid_from, valid_to);
        """,
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO knowledge_states (
            id, project_id, fact_id, scope, character, known_from_scene, source_ref, status
        )
        SELECT 'knowledge-world-' || id, project_id, id, 'world_truth', '',
               valid_from_scene, source_ref, status
        FROM story_facts
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO knowledge_states (
            id, project_id, fact_id, scope, character, known_from_scene, source_ref, status
        )
        SELECT 'knowledge-reader-' || id, project_id, id, 'reader_knowledge', '',
               reader_visible_from, source_ref, status
        FROM story_facts
        WHERE reader_visible_from IS NOT NULL
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO knowledge_states (
            id, project_id, fact_id, scope, character, known_from_scene, source_ref, status
        )
        SELECT 'knowledge-character-' || k.fact_id || '-' || lower(k.character),
               k.project_id, k.fact_id, 'character_knowledge', k.character,
               k.known_from_scene, f.source_ref, f.status
        FROM story_fact_character_knowledge k
        JOIN story_facts f ON f.project_id = k.project_id AND f.id = k.fact_id
        """
    )


def _run_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute DDL statement by statement (executescript would auto-commit)."""
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def _add_backup_restore_commits(connection: sqlite3.Connection) -> None:
    # Operational recovery metadata, never part of an exported project snapshot.
    connection.execute(
        """CREATE TABLE backup_restore_commits (
            operation_id TEXT PRIMARY KEY,
            target_project TEXT NOT NULL
        )"""
    )


def _add_snowflake_revision_history(connection: sqlite3.Connection) -> None:
    """Add append-only Snowflake revisions and losslessly backfill legacy rows."""
    _run_script(
        connection,
        """
        CREATE TABLE IF NOT EXISTS snowflake_artifact_revisions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            revision_no INTEGER NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            content TEXT NOT NULL,
            structured_payload TEXT NOT NULL DEFAULT '{}',
            schema_version INTEGER NOT NULL DEFAULT 1,
            parent_revision_id TEXT NOT NULL DEFAULT '',
            base_head_revision_id TEXT NOT NULL DEFAULT '',
            upstream_snapshot TEXT NOT NULL DEFAULT '{}',
            review_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT NOT NULL DEFAULT '',
            UNIQUE (project_id, step_number, revision_no),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_snowflake_revisions_project_step
            ON snowflake_artifact_revisions(project_id, step_number, revision_no DESC);
        CREATE INDEX IF NOT EXISTS idx_snowflake_revisions_pending
            ON snowflake_artifact_revisions(project_id, status, step_number);
        CREATE TABLE IF NOT EXISTS snowflake_artifact_heads (
            project_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            accepted_revision_id TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'missing',
            stale_reason TEXT NOT NULL DEFAULT '',
            stale_trigger_revision_id TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (project_id, step_number),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        """,
    )
    backfill_legacy_snowflake_artifacts(connection)


def backfill_legacy_snowflake_artifacts(
    connection: sqlite3.Connection,
    project_id: str | None = None,
) -> None:
    """Idempotently project legacy Snowflake rows into revision/head history."""
    now = utc_now()
    projects = (
        [project_id]
        if project_id is not None
        else [row[0] for row in connection.execute("SELECT id FROM projects").fetchall()]
    )
    for project_id in projects:
        for step_number in range(1, 11):
            connection.execute(
                """
                INSERT OR IGNORE INTO snowflake_artifact_heads (
                    project_id, step_number, accepted_revision_id, state
                ) VALUES (?, ?, '', 'missing')
                """,
                (project_id, step_number),
            )

        rows = connection.execute(
            """
            SELECT step_number, artifact, content
            FROM snowflake_artifacts
            WHERE project_id = ?
            ORDER BY step_number
            """,
            (project_id,),
        ).fetchall()
        accepted_heads = {
            int(row["step_number"]): f"snowflake:{project_id}:{row['step_number']}:r1"
            for row in rows
            if int(row["step_number"]) < 10
        }
        for row in rows:
            step_number = int(row["step_number"])
            revision_id = f"snowflake:{project_id}:{step_number}:r1"
            status = "legacy_draft" if step_number == 10 else "accepted"
            snapshot = upstream_snapshot(step_number, accepted_heads)
            connection.execute(
                """
                INSERT OR IGNORE INTO snowflake_artifact_revisions (
                    id, project_id, step_number, artifact_type, revision_no,
                    source, status, content, structured_payload, schema_version,
                    upstream_snapshot, created_at, reviewed_at
                ) VALUES (?, ?, ?, ?, 1, 'legacy', ?, ?, '{}', 1, ?, ?, ?)
                """,
                (
                    revision_id,
                    project_id,
                    step_number,
                    row["artifact"],
                    status,
                    row["content"],
                    json.dumps(snapshot, ensure_ascii=False),
                    now,
                    now if status == "accepted" else "",
                ),
            )
            if status == "accepted":
                connection.execute(
                    """
                    UPDATE snowflake_artifact_heads
                    SET accepted_revision_id = ?, state = 'approved'
                    WHERE project_id = ? AND step_number = ?
                    """,
                    (revision_id, project_id, step_number),
                )


def _extend_scene_contracts_for_snowflake(connection: sqlite3.Connection) -> None:
    for table in ("scene_contracts", "scene_proposals"):
        ensure_column(connection, table, "outcome", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, table, "information_delta", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, table, "character_state_delta", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, table, "story_thread_actions", "TEXT NOT NULL DEFAULT ''")
    ensure_column(
        connection,
        "scene_proposals",
        "blocking_errors_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )


def _add_snowflake_record_revisions(connection: sqlite3.Connection) -> None:
    """Add pageable, independently reviewable records for Snowflake steps 6–9."""
    _run_script(
        connection,
        """
        CREATE TABLE IF NOT EXISTS snowflake_record_revisions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            step_number INTEGER NOT NULL CHECK(step_number BETWEEN 6 AND 9),
            record_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            revision_no INTEGER NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            base_revision_id TEXT NOT NULL DEFAULT '',
            review_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT NOT NULL DEFAULT '',
            UNIQUE(project_id, step_number, record_id, revision_no),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_snowflake_record_revision_page
            ON snowflake_record_revisions(project_id, step_number, position, record_id, revision_no DESC);
        CREATE TABLE IF NOT EXISTS snowflake_record_heads (
            project_id TEXT NOT NULL,
            step_number INTEGER NOT NULL CHECK(step_number BETWEEN 6 AND 9),
            record_id TEXT NOT NULL,
            accepted_revision_id TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'draft',
            PRIMARY KEY(project_id, step_number, record_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        """,
    )


def _add_generation_runs(connection: sqlite3.Connection) -> None:
    """Persist safe model-call metadata without storing prompts or generated prose."""
    _run_script(
        connection,
        """
        CREATE TABLE IF NOT EXISTS generation_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            use_case TEXT NOT NULL,
            prompt_id TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            schema_name TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            requested_profile_id TEXT NOT NULL DEFAULT '',
            final_profile_id TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed')),
            error_code TEXT NOT NULL DEFAULT '',
            safe_error TEXT NOT NULL DEFAULT '',
            allow_fallback INTEGER NOT NULL DEFAULT 1,
            allow_repair INTEGER NOT NULL DEFAULT 1,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            repair_count INTEGER NOT NULL DEFAULT 0,
            fallback_count INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_generation_runs_project_created
            ON generation_runs(project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS generation_attempts (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            attempt_kind TEXT NOT NULL CHECK(attempt_kind IN ('primary', 'repair', 'fallback')),
            profile_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('succeeded', 'failed')),
            error_code TEXT NOT NULL DEFAULT '',
            retryable INTEGER NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            finish_reason TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER,
            output_tokens INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE (run_id, attempt_index),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES generation_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_generation_attempts_run
            ON generation_attempts(run_id, attempt_index);
        """,
    )


def _add_manuscript_generation_review(connection: sqlite3.Connection) -> None:
    ensure_column(
        connection, "manuscript_proposals", "generation_review_json", "TEXT NOT NULL DEFAULT 'null'"
    )


def _add_scene_record_identity(connection: sqlite3.Connection) -> None:
    for column, definition in (
        ("plan_version", "INTEGER NOT NULL DEFAULT 1"),
        ("source_record_step", "INTEGER NOT NULL DEFAULT 0"),
        ("source_record_id", "TEXT NOT NULL DEFAULT ''"),
        ("source_record_revision_id", "TEXT NOT NULL DEFAULT ''"),
    ):
        ensure_column(connection, "scene_contracts", column, definition)
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scene_source_record
        ON scene_contracts(project_id, source_record_step, source_record_id)
        WHERE source_record_id <> ''
    """)
    for operation in (
        "INSERT",
        "UPDATE OF source_record_step, source_record_id, source_record_revision_id, project_id",
    ):
        suffix = "insert" if operation == "INSERT" else "update"
        connection.execute(f"""
            CREATE TRIGGER IF NOT EXISTS validate_scene_source_{suffix}
            BEFORE {operation} ON scene_contracts
            WHEN NOT (
                (NEW.source_record_step = 0 AND NEW.source_record_id = '' AND NEW.source_record_revision_id = '')
                OR (NEW.source_record_step = 8 AND EXISTS (
                    SELECT 1 FROM snowflake_record_revisions r
                    WHERE r.project_id = NEW.project_id AND r.step_number = 8
                    AND r.record_id = NEW.source_record_id AND r.id = NEW.source_record_revision_id
                ))
            )
            BEGIN SELECT RAISE(ABORT, 'Invalid scene record source'); END
        """)


def _add_scene_update_proposals(connection: sqlite3.Connection) -> None:
    ensure_column(
        connection, "scene_proposals", "update_context_json", "TEXT NOT NULL DEFAULT '{}'"
    )
    ensure_column(
        connection, "scene_contracts", "manuscript_plan_version", "INTEGER NOT NULL DEFAULT 0"
    )
    connection.execute("""
        UPDATE scene_contracts SET manuscript_plan_version = plan_version
        WHERE EXISTS (SELECT 1 FROM manuscript_scenes m WHERE m.project_id = scene_contracts.project_id AND m.scene_id = scene_contracts.id)
    """)


MIGRATIONS: list[Migration] = [
    Migration(version=1, name="baseline_schema", apply=_apply_baseline_schema),
    Migration(version=2, name="scene_contracts_chapter_id", apply=_add_scene_contracts_chapter_id),
    Migration(version=3, name="canon_version_tracking", apply=_add_canon_version_tracking),
    Migration(
        version=4,
        name="writeback_optimistic_concurrency",
        apply=_add_writeback_optimistic_concurrency,
    ),
    Migration(version=5, name="outbox_processing_lease", apply=_add_outbox_processing_lease),
    Migration(version=6, name="narrative_state_tables", apply=_add_narrative_state_tables),
    Migration(
        version=7,
        name="narrative_domain_phase0_tables",
        apply=_add_narrative_domain_phase0_tables,
    ),
    Migration(version=8, name="backup_restore_commits", apply=_add_backup_restore_commits),
    Migration(
        version=9,
        name="snowflake_revision_history",
        apply=_add_snowflake_revision_history,
    ),
    Migration(
        version=10,
        name="snowflake_scene_contract_fields",
        apply=_extend_scene_contracts_for_snowflake,
    ),
    Migration(
        version=11,
        name="snowflake_record_revisions",
        apply=_add_snowflake_record_revisions,
    ),
    Migration(version=12, name="generation_runs", apply=_add_generation_runs),
    Migration(
        version=13, name="manuscript_generation_review", apply=_add_manuscript_generation_review
    ),
    Migration(version=14, name="scene_record_identity", apply=_add_scene_record_identity),
    Migration(version=15, name="scene_update_proposals", apply=_add_scene_update_proposals),
]

LATEST_VERSION = MIGRATIONS[-1].version

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def applied_versions(connection: sqlite3.Connection) -> set[int]:
    """Versions already recorded in schema_migrations (empty before v1)."""
    if not connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone():
        return set()
    return {int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")}


def run_migrations(connection: sqlite3.Connection) -> int:
    """Apply pending migrations in order; returns how many were applied.

    Each pending migration plus its bookkeeping row commits atomically. A
    failure rolls that migration back completely and raises a RuntimeError
    naming the failed version so startup stops with an actionable message.
    """
    connection.execute(_SCHEMA_MIGRATIONS_DDL)
    pending = [m for m in MIGRATIONS if m.version not in applied_versions(connection)]
    previous_isolation = connection.isolation_level
    try:
        # Manual transaction control: legacy implicit transactions would let
        # DDL slip out of our BEGIN..COMMIT pairs.
        connection.isolation_level = None
        for migration in sorted(pending, key=lambda item: item.version):
            try:
                connection.execute("BEGIN IMMEDIATE")
                migration.apply(connection)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, utc_now()),
                )
                connection.execute("COMMIT")
            except Exception as error:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise RuntimeError(
                    f"Database migration {migration.version:03d}_{migration.name} failed: {error}"
                ) from error
    finally:
        connection.isolation_level = previous_isolation
    return len(pending)


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Bring the database to LATEST_VERSION, then keep the demo seed."""
    run_migrations(connection)
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
