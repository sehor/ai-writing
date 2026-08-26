"""P2-07: project backup / restore package guarantees."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from app.data import SQLiteWritingDataStore
from app.data.migrations import LATEST_VERSION
from app.services.backup_service import (
    BackupConflictError,
    BackupNotFoundError,
    BackupVersionError,
    ProjectBackupService,
)


class BackupRoundtripTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.store = SQLiteWritingDataStore(root / "app.db")
        self.store.init()
        self.projects_root = root / "projects"
        self.service = ProjectBackupService(self.store, self.projects_root)
        self._seed_project()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _seed_project(self) -> None:
        with self.store.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, title, premise, current_step)"
                " VALUES ('p1', 'Backup Target', 'A project worth keeping.', 4)"
            )
            connection.execute(
                "INSERT INTO snowflake_artifacts (project_id, step_number, artifact, content)"
                " VALUES ('p1', 1, 'Premise', 'One sentence premise.')"
            )
            connection.execute(
                "INSERT INTO canon_entities (id, project_id, entity_type, name, summary,"
                " current_state, constraints, last_seen, timeline_notes, version, updated_at)"
                " VALUES ('c1', 'p1', 'character', 'Mira', 'Archivist.', 'Alive.',"
                " 'Cannot leave the archive.', 'Chapter 1', '', 2, '2026-01-01T00:00:00+00:00')"
            )
            connection.commit()
        modules_dir = self.projects_root / "p1" / "modules" / "llm_wiki" / "sources"
        modules_dir.mkdir(parents=True, exist_ok=True)
        (modules_dir / "step-1.md").write_text("# Step 1 source\n", encoding="utf-8")

    def _drop_project(self) -> None:
        with self.store.connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = 'p1'")
            connection.commit()
        import shutil

        shutil.rmtree(self.projects_root / "p1", ignore_errors=True)

    def _row_counts(self) -> dict:
        with self.store.connect() as connection:
            return {
                "projects": connection.execute(
                    "SELECT COUNT(*) FROM projects WHERE id='p1'"
                ).fetchone()[0],
                "artifacts": connection.execute(
                    "SELECT COUNT(*) FROM snowflake_artifacts WHERE project_id='p1'"
                ).fetchone()[0],
                "canon": connection.execute(
                    "SELECT COUNT(*) FROM canon_entities WHERE project_id='p1'"
                ).fetchone()[0],
            }

    def test_export_preview_import_roundtrip_restores_rows_and_files(self) -> None:
        package = self.service.export_package("p1")
        manifest = json.loads(ZipFile(io.BytesIO(package)).read("manifest.json"))
        self.assertEqual(manifest["kind"], "ai-writing-project-backup")
        self.assertEqual(manifest["schema_version"], LATEST_VERSION)
        self.assertEqual(manifest["module_file_count"], 1)

        self._drop_project()

        preview = self.service.preview_import(package)
        self.assertFalse(preview["target_exists"])
        self.assertEqual(preview["project"]["title"], "Backup Target")

        summary = self.service.import_package(package)
        self.assertFalse(summary["replaced_existing"])
        counts = self._row_counts()
        self.assertEqual((counts["projects"], counts["artifacts"], counts["canon"]), (1, 1, 1))
        restored = (
            self.projects_root / "p1" / "modules" / "llm_wiki" / "sources" / "step-1.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(restored, "# Step 1 source\n")
        # Canon optimistic-concurrency columns survived the roundtrip.
        with self.store.connect() as connection:
            version = connection.execute(
                "SELECT version FROM canon_entities WHERE id = 'c1'"
            ).fetchone()[0]
        self.assertEqual(version, 2)

    def test_import_conflicts_without_overwrite_and_replaces_with_it(self) -> None:
        package = self.service.export_package("p1")
        with self.assertRaises(BackupConflictError):
            self.service.import_package(package)
        summary = self.service.import_package(package, overwrite=True)
        self.assertTrue(summary["replaced_existing"])
        counts = self._row_counts()
        self.assertEqual(counts["projects"], 1)
        # overwrite wiped and re-created module files: exactly one copy remains
        sources = self.projects_root / "p1" / "modules" / "llm_wiki" / "sources"
        self.assertEqual([p.name for p in sources.iterdir()], ["step-1.md"])

    def test_incompatible_schema_version_is_rejected(self) -> None:
        package = bytearray(self.service.export_package("p1"))
        # Tamper: rewrite manifest.json inside the zip via re-zip.
        original = ZipFile(io.BytesIO(package))
        buffer = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        buffer.close()
        with ZipFile(buffer.name, "w") as rebuilt:
            for item in original.infolist():
                data = original.read(item.filename)
                if item.filename == "manifest.json":
                    manifest = json.loads(data)
                    manifest["schema_version"] = LATEST_VERSION + 5
                    data = json.dumps(manifest).encode("utf-8")
                rebuilt.writestr(item, data)
        tampered = Path(buffer.name).read_bytes()
        with self.assertRaises(BackupVersionError):
            self.service.preview_import(tampered)
        with self.assertRaises(BackupVersionError):
            self.service.import_package(bytes(tampered))

    def test_export_unknown_project_raises_not_found(self) -> None:
        with self.assertRaises(BackupNotFoundError):
            self.service.export_package("ghost")


if __name__ == "__main__":
    unittest.main()
