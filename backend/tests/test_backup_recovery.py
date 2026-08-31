"""Kill real child processes at restore boundaries; restart without finally blocks."""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import ProjectCreate
from app.routers.backup import get_backup_service
from app.services.backup_format import BackupError
from app.services.backup_recovery import JOURNAL, PREFIX, read_journal
from app.services.backup_service import ProjectBackupService
from app.data.unit_of_work import SqliteUnitOfWork


CHILD = r"""
import os, sys
from pathlib import Path
from unittest.mock import patch
from app.data import SQLiteWritingDataStore
from app.data.unit_of_work import SqliteUnitOfWork
from app.services import backup_files, backup_recovery
from app.services.backup_service import ProjectBackupService

database, root, package, mode = sys.argv[1:]
store = SQLiteWritingDataStore(Path(database))
store.init()
service = ProjectBackupService(store, Path(root))
rename = Path.rename
unlink = Path.unlink
commit = SqliteUnitOfWork.commit
prepare = backup_files.ModuleRestore.prepare
cleanup = backup_recovery.cleanup_staging
rmtree = backup_recovery.shutil.rmtree
write_journal = backup_files.write_journal

def die(): os._exit(86)
def renamed(path, target):
    result = rename(path, target)
    if ((mode == 'old_moved' and Path(target).name == 'old') or
        (mode == 'new_installed' and path.name == 'new') or
        (mode == 'rollback_new_removed' and Path(target).name == 'failed') or
        (mode == 'rollback_old_restored' and path.name == 'old')): die()
    return result
def unlinked(path, *args, **kwargs):
    result = unlink(path, *args, **kwargs)
    if mode == 'journal_deleted' and path.name == backup_recovery.JOURNAL: die()
    return result
def committed(uow):
    if mode == 'before_commit': die()
    commit(uow)
    if mode == 'after_commit': die()
def prepared(restore, files):
    prepare(restore, files)
    if mode == 'staged': die()
def cleaned(staging):
    cleanup(staging)
    if mode == 'stage_deleted': die()
def removed(path, *args, **kwargs):
    result = rmtree(path, *args, **kwargs)
    if mode == 'old_deleted' and Path(path).name == 'old': die()
    return result
def journal(staging, record):
    if mode == 'before_journal': die()
    return write_journal(staging, record)

with patch.object(Path, 'rename', renamed), patch.object(Path, 'unlink', unlinked), \
     patch.object(SqliteUnitOfWork, 'commit', committed), \
     patch.object(backup_files.ModuleRestore, 'prepare', prepared), \
     patch.object(backup_recovery, 'cleanup_staging', cleaned), \
     patch.object(backup_recovery.shutil, 'rmtree', removed), \
     patch.object(backup_files, 'write_journal', journal):
    if mode.startswith('rollback_'):
        service.recover_interrupted_imports()
    else:
        service.import_package(Path(package).read_bytes(), overwrite=True)
raise RuntimeError('Crash checkpoint was not reached: ' + mode)
"""


class BackupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SQLiteWritingDataStore(self.root / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Journal novel", premise="Old")
        )
        self.projects_root = self.root / "projects"
        self.modules = self.projects_root / self.project.id / "modules"
        self.modules.mkdir(parents=True)
        (self.modules / "original.md").write_bytes(b"Original file\r\n")
        self.service = ProjectBackupService(self.store, self.projects_root)
        with ZipFile(io.BytesIO(self.service.export_package(self.project.id))) as source:
            manifest = json.loads(source.read("manifest.json"))
            data = json.loads(source.read("data.json"))
        manifest["project"]["title"] = "Restored novel"
        data["tables"]["projects"][0]["title"] = "Restored novel"
        self.package = self.root / "restore.zip"
        with ZipFile(self.package, "w") as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr("data.json", json.dumps(data))
            bundle.writestr("modules/replaced.md", "Restored file\r\n")

    def snapshot(self):
        with self.store.connect() as connection:
            database = list(connection.iterdump())
        files = {
            str(p.relative_to(self.modules)): p.read_bytes()
            for p in self.modules.rglob("*")
            if p.is_file()
        }
        return database, files

    def crash(self, mode):
        env = {**os.environ, "AI_WRITING_DATA_ROOT": str(self.root)}
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                CHILD,
                str(self.store.database_path),
                str(self.projects_root),
                str(self.package),
                mode,
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 86, result.stdout + result.stderr)

    def assert_clean(self):
        self.assertEqual(list(self.projects_root.glob(".restore-*")), [])
        with self.store.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM backup_restore_commits").fetchone()[0], 0
            )

    def test_uncommitted_process_crashes_restore_exact_original_state(self):
        for mode in ("before_journal", "staged", "old_moved", "new_installed", "before_commit"):
            with self.subTest(mode=mode):
                before = self.snapshot()
                self.crash(mode)
                self.service.recover_interrupted_imports()
                self.assertEqual(self.snapshot(), before)
                self.assert_clean()
                self.assertEqual(self.service.recover_interrupted_imports(), 0)

    def test_committed_process_crashes_keep_restored_state_even_during_cleanup(self):
        for mode in ("after_commit", "old_deleted", "journal_deleted", "stage_deleted"):
            with self.subTest(mode=mode):
                self.crash(mode)
                self.service.recover_interrupted_imports()
                self.assertEqual(self.store.get_project(self.project.id).title, "Restored novel")
                self.assertEqual(self.snapshot()[1], {"replaced.md": b"Restored file\r\n"})
                self.assert_clean()

    def test_new_project_import_crash_removes_uncommitted_module_files(self):
        with self.store.connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (self.project.id,))
        shutil.rmtree(self.modules.parent)
        before = self.snapshot()
        self.crash("new_installed")
        self.service.recover_interrupted_imports()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.modules.parent.exists())
        self.assert_clean()

    def test_recovery_itself_can_be_killed_and_restarted(self):
        for mode in ("rollback_new_removed", "rollback_old_restored"):
            with self.subTest(mode=mode):
                before = self.snapshot()
                self.crash("new_installed")
                self.crash(mode)
                self.service.recover_interrupted_imports()
                self.assertEqual(self.snapshot(), before)
                self.assert_clean()

    def test_startup_recovers_before_dispatcher_or_requests(self):
        before = self.snapshot()
        self.crash("new_installed")
        dispatcher = Mock(stop=AsyncMock())

        def build(_app):
            self.assertEqual(self.snapshot(), before)
            self.assert_clean()
            return dispatcher

        app.dependency_overrides[get_data_store] = lambda: self.store
        app.dependency_overrides[get_backup_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.clear)
        with patch("app.main.build_app_outbox_dispatcher", side_effect=build):
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/projects").status_code, 200)
        dispatcher.start.assert_called_once()
        dispatcher.stop.assert_awaited_once()

    def test_damaged_or_foreign_journal_stops_startup_without_touching_data(self):
        self.crash("new_installed")
        staging = next(self.projects_root.glob(PREFIX + "*"))
        record = read_journal(staging, self.store.database_path)
        before = self.snapshot()
        original = (staging / JOURNAL).read_bytes()
        for change in (
            {"project_id": "../outside"},
            {"database": str(self.root / "other.db")},
            {"operation_id": "another"},
            {"phase": "unknown"},
        ):
            with self.subTest(change=change):
                (staging / JOURNAL).write_text(json.dumps({**record, **change}), encoding="utf-8")
                with self.assertRaises(BackupError):
                    self.service.recover_interrupted_imports()
                self.assertEqual(self.snapshot(), before)
                self.assertTrue((staging / "old" / "original.md").exists())
        (staging / JOURNAL).write_bytes(b"{broken")
        app.dependency_overrides[get_data_store] = lambda: self.store
        app.dependency_overrides[get_backup_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.clear)
        with patch("app.main.build_app_outbox_dispatcher") as build:
            with self.assertRaises(BackupError), TestClient(app):
                pass
            build.assert_not_called()
        (staging / JOURNAL).write_bytes(original)
        self.service.recover_interrupted_imports()

    def test_commit_acknowledgment_error_cannot_roll_back_committed_files(self):
        original = SqliteUnitOfWork.commit

        def committed_then_error(uow):
            original(uow)
            raise RuntimeError("lost commit acknowledgment")

        with patch.object(SqliteUnitOfWork, "commit", committed_then_error):
            result = self.service.import_package(self.package.read_bytes(), overwrite=True)
        self.assertTrue(result["replaced_existing"])
        self.assertEqual(self.store.get_project(self.project.id).title, "Restored novel")
        self.assertEqual(self.snapshot()[1], {"replaced.md": b"Restored file\r\n"})
        self.assert_clean()

    def test_missing_commit_cannot_be_reported_as_success(self):
        before = self.snapshot()
        with patch.object(SqliteUnitOfWork, "commit", return_value=None):
            with self.assertRaises(BackupError):
                self.service.import_package(self.package.read_bytes(), overwrite=True)
        self.assertEqual(self.snapshot(), before)
        self.assert_clean()

    def test_committed_restore_with_missing_files_fails_closed(self):
        self.crash("after_commit")
        staging = next(self.projects_root.glob(PREFIX + "*"))
        # Simulate a filesystem problem after the commit: do not silently report
        # success or put old module files beside the new database.
        displaced = self.root / "displaced-modules"
        self.modules.rename(displaced)
        with self.assertRaises(BackupError):
            self.service.recover_interrupted_imports()
        self.assertTrue((staging / "old" / "original.md").exists())
        self.assertFalse(self.modules.exists())
        self.assertEqual(self.store.get_project(self.project.id).title, "Restored novel")
        displaced.rename(self.modules)
        self.service.recover_interrupted_imports()
        self.assert_clean()

    def test_deferred_rollback_cleanup_does_not_remove_later_author_files(self):
        shutil.rmtree(self.modules)
        self.crash("new_installed")
        with patch("app.services.backup_recovery.cleanup_staging", side_effect=OSError("busy")):
            self.service.recover_interrupted_imports()
        self.modules.mkdir(parents=True)
        (self.modules / "later.md").write_text("Later author work", encoding="utf-8")
        self.service.recover_interrupted_imports()
        self.assertEqual((self.modules / "later.md").read_text(), "Later author work")
        self.assert_clean()

    def test_legacy_unjournaled_restore_is_preserved_for_manual_recovery(self):
        legacy = self.projects_root / ".restore-legacy"
        legacy.mkdir()
        (legacy / "old").mkdir()
        (legacy / "old" / "author.md").write_text("Do not delete", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(BackupError):
            self.service.recover_interrupted_imports()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue((legacy / "old" / "author.md").exists())

    def test_commit_marker_is_not_in_exported_project_data(self):
        with patch("app.services.backup_recovery.cleanup_staging", side_effect=OSError("busy")):
            self.service.import_package(self.package.read_bytes(), overwrite=True)
        with ZipFile(io.BytesIO(self.service.export_package(self.project.id))) as bundle:
            data = json.loads(bundle.read("data.json"))
            self.assertNotIn("backup_restore_commits", data["tables"])
        self.service.recover_interrupted_imports()
        self.assert_clean()
