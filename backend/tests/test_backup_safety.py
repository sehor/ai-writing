"""Regression fixtures contain no user projects; failures must preserve both stores."""

import io
import json
import sqlite3
import tempfile
import unittest
import warnings
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from app.data import SQLiteWritingDataStore
from app.data.unit_of_work import SqliteUnitOfWork
from app.data.repositories.outbox import OutboxRepository
from app.outbox.service import OutboxService
from app.models import ManuscriptProposalCreate, ProjectCreate, SceneContractCreate
from app.services.backup_format import NARRATIVE_TABLES, TABLES_IN_ORDER
from app.services.backup_records import RECORD_READERS
from app.services.backup_service import BackupConflictError, BackupError, ProjectBackupService


class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SQLiteWritingDataStore(self.root / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Backup safety", premise="Probe")
        )
        self.project_id = self.project.id
        self.scene = self.store.create_scene_contract(
            self.project_id, SceneContractCreate(sequence=1, title="Door")
        )
        self.projects_root = self.root / "projects"
        self.file = self.projects_root / self.project_id / "modules" / "old.md"
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b"Original file\r\n")
        self.service = ProjectBackupService(self.store, self.projects_root)

    def snapshot(self):
        with self.store.connect() as connection:
            database = list(connection.iterdump())
        files = {
            str(p.relative_to(self.projects_root)): p.read_bytes()
            for p in self.projects_root.rglob("*")
            if p.is_file()
        }
        return database, files

    def rewrite(self, edit=lambda m, d: None, files=None):
        with ZipFile(io.BytesIO(self.service.export_package(self.project_id))) as original:
            manifest = json.loads(original.read("manifest.json"))
            data = json.loads(original.read("data.json"))
            entries = [
                (n, original.read(n)) for n in original.namelist() if n.startswith("modules/")
            ]
        edit(manifest, data)
        if files is not None:
            entries = files
            manifest["module_file_count"] = len(entries)
        buffer = io.BytesIO()
        with warnings.catch_warnings(), ZipFile(buffer, "w") as bundle:
            warnings.simplefilter("ignore", UserWarning)
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr("data.json", json.dumps(data))
            for name, content in entries:
                member = ZipInfo()
                member.filename = name
                bundle.writestr(member, content)
        return buffer.getvalue()

    def assert_rejected_without_changes(self, package):
        before = self.snapshot()
        with self.assertRaises(BackupError):
            self.service.preview_import(package)
        with self.assertRaises(BackupError):
            self.service.import_package(package, overwrite=True)
        self.assertEqual(self.snapshot(), before)

    def test_every_project_table_has_an_explicit_backup_policy(self):
        with self.store.connect() as connection:
            tables = [
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            scoped = {
                t
                for t in tables
                if "project_id" in {r[1] for r in connection.execute(f'PRAGMA table_info("{t}")')}
            }
        self.assertEqual(scoped | {"projects"}, set(TABLES_IN_ORDER))
        self.assertEqual(set(RECORD_READERS), set(TABLES_IN_ORDER))

    def test_all_narrative_rows_survive_overwrite_and_new_database_restore(self):
        with self.store.connect() as c:
            c.execute(
                "INSERT INTO story_facts(id,project_id,subject,predicate,value,valid_from_scene) VALUES('f',?,'Mira','knows','Secret',1)",
                (self.project_id,),
            )
            c.execute(
                "INSERT INTO story_fact_character_knowledge VALUES(?,'f','Mira',1)",
                (self.project_id,),
            )
            c.execute(
                "INSERT INTO knowledge_states(id,project_id,fact_id,scope,character,known_from_scene) VALUES('k',?,'f','character_knowledge','Mira',1)",
                (self.project_id,),
            )
            c.execute(
                "INSERT INTO narrative_relations(id,project_id,source,target,relation,valid_from) VALUES('r',?,'Mira','Door','opens',1)",
                (self.project_id,),
            )
            c.execute(
                "INSERT INTO story_threads(id,project_id,thread_type,title,status) VALUES('t',?,'promise','Door','planted')",
                (self.project_id,),
            )
            c.execute(
                "INSERT INTO story_thread_events(id,project_id,thread_id,scene_id,action) VALUES('e',?,'t',?,'plant')",
                (self.project_id, self.scene.id),
            )
        package = self.service.export_package(self.project_id)
        before = self.snapshot()
        self.service.import_package(package, overwrite=True)
        self.assertEqual(self.snapshot(), before)
        target = SQLiteWritingDataStore(self.root / "target.db")
        target.init()
        ProjectBackupService(target, self.root / "target-projects").import_package(package)
        with self.store.connect() as source, target.connect() as restored:
            for table in NARRATIVE_TABLES:
                expected = [tuple(row) for row in source.execute(f'SELECT * FROM "{table}"')]
                self.assertEqual(
                    [tuple(row) for row in restored.execute(f'SELECT * FROM "{table}"')], expected
                )

    def test_invalid_project_ids_never_reach_live_database(self):
        for project_id in ("../escape", "C:escape", "CON", "bad\\id", "bad/id", "x\nheader"):
            with self.subTest(project_id=project_id):
                self.assert_rejected_without_changes(
                    self.rewrite(lambda m, d: m["project"].update(id=project_id))
                )

    def test_unsafe_module_paths_and_collisions_fail_in_preview(self):
        for path in (
            "../escape",
            "/absolute",
            "a/../../escape",
            "C:/escape",
            "a\\b",
            "a//b",
            "NUL.txt",
            "name.",
        ):
            with self.subTest(path=path):
                self.assert_rejected_without_changes(
                    self.rewrite(files=[("modules/" + path, b"text")])
                )
        for entries in (
            [("modules/a", b"one"), ("modules/a", b"two")],
            [("modules/A", b"one"), ("modules/a", b"two")],
            [("modules/a", b"one"), ("modules/a/b", b"two")],
            [("modules/a", b"\xff")],
        ):
            self.assert_rejected_without_changes(self.rewrite(files=entries))

    def test_unknown_tables_columns_counts_and_cross_project_rows_fail_in_preview(self):
        other = self.store.create_project(ProjectCreate(title="Other", premise="Other"))
        edits = [
            lambda m, d: d["tables"].update(unknown=[]),
            lambda m, d: d["tables"]["projects"][0].update(unknown="x"),
            lambda m, d: m["project"]["row_counts"].update(projects=2),
            lambda m, d: m.update(module_file_count=100),
            lambda m, d: d["tables"]["scene_contracts"][0].update(project_id=other.id),
            lambda m, d: d["tables"]["projects"][0].update(id=other.id),
            lambda m, d: d["tables"].pop("story_facts"),
        ]
        for edit in edits:
            with self.subTest(edit=edit):
                self.assert_rejected_without_changes(self.rewrite(edit))

    def test_foreign_key_errors_fail_before_any_live_write(self):
        def edit(m, d):
            d["tables"]["knowledge_states"] = [
                {
                    "id": "k",
                    "project_id": self.project_id,
                    "fact_id": "missing",
                    "scope": "reader",
                    "known_from_scene": 1,
                }
            ]
            m["project"]["row_counts"]["knowledge_states"] = 1

        self.assert_rejected_without_changes(self.rewrite(edit))

    def test_legacy_package_warns_and_cannot_overwrite(self):
        def legacy(m, d):
            m["format_version"] = 1
            m.pop("tables")
            for table in NARRATIVE_TABLES:
                d["tables"].pop(table)
                m["project"]["row_counts"].pop(table)

        package = self.rewrite(legacy)
        preview = self.service.preview_import(package)
        self.assertTrue(preview["legacy_incomplete"])
        self.assertFalse(preview["can_overwrite"])
        before = self.snapshot()
        with self.assertRaises(BackupConflictError):
            self.service.import_package(package, overwrite=True)
        self.assertEqual(self.snapshot(), before)
        target = SQLiteWritingDataStore(self.root / "legacy.db")
        target.init()
        result = ProjectBackupService(target, self.root / "legacy-projects").import_package(package)
        self.assertTrue(result["legacy_incomplete"])

    def test_database_failure_after_delete_restores_original_state(self):
        package = self.rewrite()
        before = self.snapshot()

        def broken_restore(connection, project_id, tables):
            connection.execute("DELETE FROM projects WHERE id=?", (project_id,))
            raise sqlite3.IntegrityError("injected halfway through restore")

        with patch.object(self.service, "_restore_database", side_effect=broken_restore):
            with self.assertRaises(BackupError):
                self.service.import_package(package, overwrite=True)
        self.assertEqual(self.snapshot(), before)

    def test_staging_and_directory_switch_failures_preserve_original_state(self):
        package = self.rewrite(files=[("modules/new.md", b"New")])
        before = self.snapshot()
        original_rename = Path.rename

        def fail_new_switch(path, target):
            if path.name == "new":
                raise OSError("injected directory switch failure")
            return original_rename(path, target)

        for failure in (
            patch.object(Path, "write_bytes", side_effect=OSError("injected disk full")),
            patch.object(Path, "rename", fail_new_switch),
        ):
            with failure, self.assertRaises(BackupError):
                self.service.import_package(package, overwrite=True)
            self.assertEqual(self.snapshot(), before)

    def test_commit_failure_restores_old_directory_and_database(self):
        package = self.rewrite(files=[("modules/new.md", b"New")])
        before = self.snapshot()
        with patch.object(
            SqliteUnitOfWork, "commit", side_effect=sqlite3.OperationalError("commit failed")
        ):
            with self.assertRaises(BackupError):
                self.service.import_package(package, overwrite=True)
        self.assertEqual(self.snapshot(), before)

    def test_export_keeps_one_snapshot_during_a_concurrent_author_commit(self):
        original_connect = self.store.connect
        fired = False
        store, project_id, scene_id = self.store, self.project_id, self.scene.id

        class ConcurrentConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, args=()):
                nonlocal fired
                if 'FROM "manuscript_scenes"' in sql and not fired:
                    fired = True
                    proposal = store.create_manuscript_proposal(
                        project_id,
                        ManuscriptProposalCreate(
                            scene_id=scene_id, title="Concurrent", content="New text"
                        ),
                    )
                    store.accept_manuscript_proposal(project_id, proposal.id)
                return self.connection.execute(sql, args)

        @contextmanager
        def intercepted():
            with original_connect() as connection:
                yield ConcurrentConnection(connection)

        with patch.object(self.store, "connect", intercepted):
            package = self.service.export_package(project_id)
        self.assertTrue(fired)
        target = SQLiteWritingDataStore(self.root / "snapshot.db")
        target.init()
        ProjectBackupService(target, self.root / "snapshot-projects").import_package(package)
        self.assertEqual(len(store.list_manuscript_revisions(project_id)), 1)
        self.assertEqual(len(target.list_manuscript_revisions(project_id)), 0)

    def test_package_limits_are_checked_before_decompression(self):
        package = self.rewrite()
        for limit in ("MAX_PACKAGE_BYTES", "MAX_EXPANDED_BYTES", "MAX_MEMBERS"):
            with patch("app.services.backup_format." + limit, 1):
                self.assert_rejected_without_changes(package)

    def test_export_never_returns_a_package_larger_than_import_supports(self):
        for limit in ("MAX_PACKAGE_BYTES", "MAX_EXPANDED_BYTES", "MAX_MEMBERS"):
            with self.subTest(limit=limit), patch("app.services.backup_service." + limit, 1):
                with self.assertRaises(BackupError):
                    self.service.export_package(self.project_id)

    def test_sql_valid_but_unreadable_domain_values_are_rejected(self):
        proposal = self.store.create_manuscript_proposal(
            self.project_id,
            ManuscriptProposalCreate(scene_id=self.scene.id, title="Draft", content="Prose"),
        )
        self.assertIsNotNone(proposal)
        for column, value in (
            ("status", "unknown_state"),
            ("checklist_json", "not json"),
            ("checklist_json", '{"wrong":"shape"}'),
        ):

            def corrupt(manifest, data):
                data["tables"]["manuscript_proposals"][0][column] = value

            with self.subTest(column=column, value=value):
                self.assert_rejected_without_changes(self.rewrite(edit=corrupt))

    def test_case_alias_cannot_overwrite_another_projects_module_directory(self):
        def rename(manifest, data):
            alias = self.project_id.upper()
            manifest["project"]["id"] = alias
            for table, rows in data["tables"].items():
                for row in rows:
                    row["id" if table == "projects" else "project_id"] = alias

        self.assert_rejected_without_changes(self.rewrite(edit=rename))

    def test_orphan_module_files_still_require_overwrite_confirmation(self):
        package = self.service.export_package(self.project_id)
        with self.store.connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (self.project_id,))
        before = self.snapshot()
        self.assertTrue(self.service.preview_import(package)["target_exists"])
        with self.assertRaises(BackupConflictError):
            self.service.import_package(package)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.service.import_package(package, overwrite=True)["replaced_existing"])

    def test_restore_waits_for_running_job_and_does_not_keep_its_stale_files(self):
        package = self.service.export_package(self.project_id)
        with self.store.connect() as connection:
            job_id = OutboxRepository(connection).insert(
                project_id=self.project_id,
                job_type="llm_wiki_ingest",
                aggregate_type="test",
                aggregate_id="test",
                payload={"project_id": self.project_id},
                idempotency_key="test",
            )
        entered, release, restoring = threading.Event(), threading.Event(), threading.Event()
        stale = self.file.parent / "stale.md"

        def handler(context, payload):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            stale.write_text("old worker", encoding="utf-8")

        def restore():
            restoring.set()
            return self.service.import_package(package, overwrite=True)

        with patch.dict("app.outbox.service.OUTBOX_HANDLERS", {"llm_wiki_ingest": handler}):
            with ThreadPoolExecutor(max_workers=2) as executor:
                worker = executor.submit(
                    OutboxService(self.store, None).process_job, self.project_id, job_id
                )
                self.assertTrue(entered.wait(3))
                importing = executor.submit(restore)
                self.assertTrue(restoring.wait(3))
                try:
                    self.assertFalse(importing.done())
                finally:
                    release.set()
                worker.result(timeout=5)
                importing.result(timeout=5)
        self.assertFalse(stale.exists())
        self.assertEqual(self.file.read_bytes(), b"Original file\r\n")
