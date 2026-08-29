"""P2-06: versioned schema migration guarantees.

Covers the acceptance matrix from the improvement plan: empty-database
upgrade, legacy-database upgrade, repeated execution, mid-migration failure
rollback, and preservation of pre-existing rows.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.data.migrations import (
    LATEST_VERSION,
    MIGRATIONS,
    Migration,
    applied_versions,
    initialize_schema,
    run_migrations,
)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


class MigrationTests(unittest.TestCase):
    def test_empty_database_reaches_latest_version(self) -> None:
        # 空数据库升级: a fresh database applies every migration once.
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                applied = run_migrations(connection)
                self.assertEqual(applied, len(MIGRATIONS))
                self.assertEqual(applied_versions(connection), set(range(1, LATEST_VERSION + 1)))
                expected_tables = {
                    "projects",
                    "canon_entities",
                    "scene_contracts",
                    "manuscript_chapters",
                    "writeback_proposals",
                    "outbox_jobs",
                    "analysis_runs",
                    "scene_proposals",
                    "story_facts",
                    "knowledge_states",
                    "narrative_relations",
                    "schema_migrations",
                }
                self.assertTrue(expected_tables <= _table_names(connection))
                self.assertTrue({"chapter_id"} <= _column_names(connection, "scene_contracts"))
                self.assertTrue(
                    {"version", "updated_at"} <= _column_names(connection, "canon_entities")
                )
            finally:
                connection.close()

    def test_legacy_database_converges_and_keeps_rows(self) -> None:
        # 旧数据库升级 + 数据不丢失: an old-era database upgrades in place.
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                # A pre-P1-02 era database: no canon version tracking, no
                # outbox / analysis / scene_proposals tables, no bookkeeping.
                connection.executescript(
                    """
                    CREATE TABLE projects (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        premise TEXT NOT NULL,
                        current_step INTEGER NOT NULL
                    );
                    CREATE TABLE canon_entities (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        current_state TEXT NOT NULL,
                        constraints TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        timeline_notes TEXT NOT NULL,
                        UNIQUE (project_id, entity_type, name)
                    );
                    INSERT INTO projects (id, title, premise, current_step)
                    VALUES ('legacy', 'Legacy Project', 'Old premise.', 2);
                    """
                )

                applied = run_migrations(connection)

                self.assertEqual(applied, len(MIGRATIONS))
                self.assertEqual(applied_versions(connection), set(range(1, LATEST_VERSION + 1)))
                self.assertTrue(
                    {"version", "updated_at"} <= _column_names(connection, "canon_entities")
                )
                row = connection.execute(
                    "SELECT id, title, premise, current_step FROM projects WHERE id = 'legacy'"
                ).fetchone()
                self.assertEqual(tuple(row), ("legacy", "Legacy Project", "Old premise.", 2))
            finally:
                connection.close()

    def test_repeated_execution_is_a_noop(self) -> None:
        # 迁移重复执行: re-running records nothing new and keeps data.
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                initialize_schema(connection)
                before = sorted(applied_versions(connection))
                connection.execute(
                    "INSERT INTO projects (id, title, premise, current_step)"
                    " VALUES ('keep', 'Keep', 'p', 1)"
                )
                connection.commit()

                again = run_migrations(connection)

                self.assertEqual(again, 0)
                self.assertEqual(sorted(applied_versions(connection)), before)
                self.assertIsNotNone(
                    connection.execute("SELECT 1 FROM projects WHERE id = 'keep'").fetchone()
                )
            finally:
                connection.close()

    def test_failed_migration_rolls_back_fully_and_names_version(self) -> None:
        # 迁移中途失败回滚: partial changes vanish and startup gets a clear error.

        def _boom(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE migration_probe (id TEXT PRIMARY KEY)")
            raise RuntimeError("injected failure")

        failing = Migration(version=LATEST_VERSION + 1, name="boom", apply=_boom)
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                with mock.patch.object(
                    __import__("app.data.migrations", fromlist=["MIGRATIONS"]),
                    "MIGRATIONS",
                    [*MIGRATIONS, failing],
                ):
                    with self.assertRaises(RuntimeError) as caught:
                        run_migrations(connection)

                self.assertIn(f"{LATEST_VERSION + 1:03d}_boom", str(caught.exception))
                self.assertIn("injected failure", str(caught.exception))
                # The failed version is not recorded and its partial DDL is gone.
                self.assertNotIn(LATEST_VERSION + 1, applied_versions(connection))
                self.assertNotIn("migration_probe", _table_names(connection))
                # The successful prefix remains applied.
                self.assertEqual(applied_versions(connection), set(range(1, LATEST_VERSION + 1)))
                # The connection is usable again after the rollback.
                connection.execute("CREATE TABLE sanity_check (id INTEGER PRIMARY KEY)")
            finally:
                connection.close()

    def test_initialize_schema_keeps_demo_seed_single(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                initialize_schema(connection)
                initialize_schema(connection)
                count = connection.execute(
                    "SELECT COUNT(*) FROM projects WHERE id = 'demo-novel'"
                ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                connection.close()

    def test_narrative_domain_migration_backfills_existing_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                for migration in MIGRATIONS[:6]:
                    migration.apply(connection)
                connection.execute(
                    "INSERT INTO projects (id, title, premise, current_step)"
                    " VALUES ('p1', 'Legacy narrative', 'p', 1)"
                )
                connection.execute(
                    """
                    INSERT INTO story_facts (
                        id, project_id, subject, predicate, value, valid_from_scene,
                        valid_to_scene, reader_visible_from, source_ref, status
                    ) VALUES ('f1', 'p1', 'letter', 'author', 'queen', 1, NULL, 80,
                              'canon:f1', 'confirmed')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO story_fact_character_knowledge (
                        project_id, fact_id, character, known_from_scene
                    ) VALUES ('p1', 'f1', 'Mira', 84)
                    """
                )

                MIGRATIONS[6].apply(connection)

                states = connection.execute(
                    """
                    SELECT scope, character, known_from_scene, source_ref
                    FROM knowledge_states
                    WHERE project_id = 'p1' AND fact_id = 'f1'
                    ORDER BY scope
                    """
                ).fetchall()
                self.assertEqual(
                    [tuple(row) for row in states],
                    [
                        ("character_knowledge", "Mira", 84, "canon:f1"),
                        ("reader_knowledge", "", 80, "canon:f1"),
                        ("world_truth", "", 1, "canon:f1"),
                    ],
                )
            finally:
                connection.close()

    def test_outbox_jobs_gain_processing_started_at_column(self) -> None:
        # P1-02: claim lease bookkeeping exists on fresh databases and
        # pre-existing rows keep an empty stamp.
        with tempfile.TemporaryDirectory() as temp_dir:
            connection = sqlite3.connect(Path(temp_dir) / "app.db")
            connection.row_factory = sqlite3.Row
            try:
                self.assertEqual(run_migrations(connection), len(MIGRATIONS))
                self.assertIn("processing_started_at", _column_names(connection, "outbox_jobs"))
                connection.execute(
                    "INSERT INTO projects (id, title, premise, current_step)"
                    " VALUES ('legacy', 'Legacy', 'p', 1)"
                )
                insert_job = (
                    "INSERT INTO outbox_jobs ("
                    " id, project_id, job_type, aggregate_type, aggregate_id,"
                    " payload_json, idempotency_key, status, created_at)"
                    " VALUES ('job-1', 'legacy', 'llm_wiki_ingest',"
                    " 'manuscript_revision', 'rev-1', '{}', 'k-1', 'pending',"
                    " '2026-01-01T00:00:00+00:00')"
                )
                connection.execute(insert_job)
                row = connection.execute(
                    "SELECT processing_started_at FROM outbox_jobs WHERE id = 'job-1'"
                ).fetchone()
                self.assertEqual(row["processing_started_at"], "")
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
