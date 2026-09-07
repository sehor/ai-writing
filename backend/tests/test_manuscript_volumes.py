"""AUD-21: volumes organize chapters without owning their lifetime or story time."""

import io
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient
from app.data import SQLiteWritingDataStore, get_data_store
from app.data.migrations import MIGRATIONS
from app.main import app
from app.models import (
    ManuscriptChapterCreate,
    ManuscriptProposalCreate,
    ProjectCreate,
    SceneContractCreate,
)
from app.services.backup_service import ProjectBackupService
from app.services.manuscript_service import ManuscriptService
from app.cognition.registry import CognitionRegistry


class ManuscriptVolumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SQLiteWritingDataStore(self.root / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Volumes", premise="A long novel")
        )
        self.other = self.store.create_project(
            ProjectCreate(title="Other", premise="Another novel")
        )
        self.chapter = self.store.create_manuscript_chapter(
            self.project.id, ManuscriptChapterCreate(sequence=1, title="Original")
        )
        self.scene = self.store.create_scene_contract(
            self.project.id,
            SceneContractCreate(sequence=1, title="Opening", chapter_id=self.chapter.id),
        )
        proposal = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(
                scene_id=self.scene.id, title="Opening", content="ORIGINAL_TEXT"
            ),
        )
        self.store.accept_manuscript_proposal(self.project.id, proposal.id)
        self.scene = self.store.get_scene_contract(self.project.id, self.scene.id)
        self.revisions = self.store.list_manuscript_revisions(self.project.id)
        app.dependency_overrides[get_data_store] = lambda: self.store
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = f"/api/projects/{self.project.id}/manuscript"

    def volume(self, title="Volume one", sequence=1):
        response = self.client.post(
            f"{self.url}/volumes", json={"title": title, "sequence": sequence}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def assign(self, volume_id):
        return self.client.put(
            f"{self.url}/chapters/{self.chapter.id}/volume", json={"volume_id": volume_id}
        )

    def test_create_rename_reorder_move_unassign_and_delete_are_nondestructive(self):
        first = self.volume()
        second = self.volume("Volume two", 2)
        self.assertEqual(self.assign(first["id"]).status_code, 200)
        self.assertEqual(self.assign(second["id"]).status_code, 200)
        changed = self.client.put(
            f"{self.url}/volumes/{second['id']}", json={"title": "Renamed", "sequence": 1}
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["chapter_ids"], [self.chapter.id])
        self.assertEqual(self.assign("").status_code, 200)
        self.assertEqual(self.assign(first["id"]).status_code, 200)
        self.assertEqual(self.client.delete(f"{self.url}/volumes/{first['id']}").status_code, 204)
        self.assertEqual(self.store.list_manuscript_chapters(self.project.id), [self.chapter])
        self.assertEqual(self.store.list_scene_contracts(self.project.id), [self.scene])
        self.assertEqual(self.store.list_manuscript_revisions(self.project.id), self.revisions)
        self.assertEqual(self.client.get(f"{self.url}/volumes").json()[0]["chapter_ids"], [])

    def test_foreign_missing_and_invalid_volume_assignments_are_rejected(self):
        volume = self.volume()
        foreign = self.store.create_manuscript_chapter(
            self.other.id, ManuscriptChapterCreate(sequence=1, title="Private")
        )
        self.assertEqual(
            self.client.put(
                f"{self.url}/chapters/{foreign.id}/volume", json={"volume_id": volume["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(self.assign("missing").status_code, 404)
        for body in ({"title": " ", "sequence": 1}, {"title": "Bad", "sequence": 1000}):
            self.assertEqual(self.client.post(f"{self.url}/volumes", json=body).status_code, 422)
        with self.store.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO manuscript_volume_chapters (project_id, chapter_id, volume_id) VALUES (?, ?, ?)",
                    (self.project.id, foreign.id, volume["id"]),
                )

    def test_export_orders_by_volume_then_chapter_and_keeps_unassigned_text(self):
        later = self.volume("Later volume", 2)
        earlier = self.volume("Earlier volume", 1)
        self.assign(later["id"])
        chapter = self.store.create_manuscript_chapter(
            self.project.id, ManuscriptChapterCreate(sequence=2, title="Second chapter")
        )
        scene = self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=2, title="Second", chapter_id=chapter.id)
        )
        proposal = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(scene_id=scene.id, title="Second", content="SECOND_TEXT"),
        )
        self.store.accept_manuscript_proposal(self.project.id, proposal.id)
        self.client.put(
            f"{self.url}/chapters/{chapter.id}/volume", json={"volume_id": earlier["id"]}
        )
        service = ManuscriptService(self.store, CognitionRegistry([]))
        exported = service.export(self.project.id).content
        self.assertLess(exported.index("Earlier volume"), exported.index("Later volume"))
        self.assertLess(exported.index("SECOND_TEXT"), exported.index("ORIGINAL_TEXT"))
        self.assign("")
        exported = service.export(self.project.id).content
        self.assertIn("Unassigned Chapters", exported)
        self.assertEqual(exported.count("ORIGINAL_TEXT"), 1)

    def test_backup_preserves_membership_and_pre_volume_backup_stays_unassigned(self):
        volume = self.volume()
        self.assign(volume["id"])
        service = ProjectBackupService(self.store, self.root / "projects")
        package = service.export_package(self.project.id)
        restored = SQLiteWritingDataStore(self.root / "restored.db")
        restored.init()
        importer = ProjectBackupService(restored, self.root / "restored")
        importer.import_package(package)
        self.assertEqual(
            restored.list_manuscript_volumes(self.project.id)[0].chapter_ids, [self.chapter.id]
        )
        source = ZipFile(io.BytesIO(package))
        manifest = json.loads(source.read("manifest.json"))
        data = json.loads(source.read("data.json"))
        manifest["schema_version"] = 18
        for table in ("manuscript_volumes", "manuscript_volume_chapters"):
            manifest["tables"].remove(table)
            manifest["project"]["row_counts"].pop(table)
            data["tables"].pop(table)
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr("data.json", json.dumps(data))
        importer.import_package(buffer.getvalue(), overwrite=True)
        self.assertEqual(restored.list_manuscript_volumes(self.project.id), [])
        self.assertEqual(restored.list_manuscript_revisions(self.project.id), self.revisions)

    def test_migration_from_18_preserves_existing_author_ids(self):
        path = self.root / "old.db"
        old = SQLiteWritingDataStore(path)
        with patch("app.data.migrations.MIGRATIONS", [m for m in MIGRATIONS if m.version <= 18]):
            old.init()
        project = old.create_project(ProjectCreate(title="Old", premise="Preserve"))
        chapter = old.create_manuscript_chapter(
            project.id, ManuscriptChapterCreate(sequence=1, title="Existing")
        )
        old.init()
        self.assertEqual(old.list_manuscript_chapters(project.id), [chapter])
        self.assertEqual(old.list_manuscript_volumes(project.id), [])
