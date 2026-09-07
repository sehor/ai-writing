"""Lightweight capacity regression; larger tiers are explicit benchmark jobs."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from app.models import ManuscriptSceneUpdate, SceneContractCreate
from app.services.backup_service import ProjectBackupService, BackupError
from scripts.benchmark_longform import seed_project, measure_backend


class LongformBenchmarkTests(unittest.TestCase):
    def test_small_fixture_preserves_all_text_history_and_membership(self):
        with TemporaryDirectory() as directory:
            store, fixture = seed_project(Path(directory), scene_count=20, chars=2000, revisions=3)
            project = fixture["project_id"]
            self.assertEqual(len(store.list_scene_contracts(project)), 20)
            self.assertEqual(len(store.list_manuscript_revisions(project)), 60)
            self.assertEqual(
                sum(len(scene.content) for scene in store.list_manuscript_scenes(project)), 40000
            )
            result = measure_backend(store, fixture, Path(directory), repeats=1)
            self.assertGreater(result["backup_bytes"], 0)
            self.assertEqual(result["restored_revision_count"], 60)
            self.assertIn("sqlite_history_raw", result["timings_ms"])

    def test_fixture_refuses_existing_data_root(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "author.txt").write_text("Never overwrite", encoding="utf-8")
            with self.assertRaises(ValueError):
                seed_project(path, scene_count=20)
            self.assertEqual((path / "author.txt").read_text(encoding="utf-8"), "Never overwrite")

    def test_hard_field_limits_reject_instead_of_truncating_author_text(self):
        self.assertEqual(SceneContractCreate(sequence=999, title="Boundary").sequence, 999)
        with self.assertRaises(ValidationError):
            SceneContractCreate(sequence=1000, title="Reject")
        text = "文" * 40000
        self.assertEqual(
            ManuscriptSceneUpdate(title="Max", content=text, expected_scene_version=1).content, text
        )
        with self.assertRaises(ValidationError):
            ManuscriptSceneUpdate(title="Reject", content=text + "末", expected_scene_version=1)

    def test_backup_over_budget_fails_explicitly_without_modifying_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store, fixture = seed_project(root, scene_count=2)
            before = store.list_manuscript_scenes(fixture["project_id"])
            with patch("app.services.backup_service.MAX_EXPANDED_BYTES", 1):
                with self.assertRaises(BackupError):
                    ProjectBackupService(store, root / "projects").export_package(
                        fixture["project_id"]
                    )
            self.assertEqual(store.list_manuscript_scenes(fixture["project_id"]), before)
