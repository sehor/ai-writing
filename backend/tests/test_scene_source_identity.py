from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.data.unit_of_work import SqliteUnitOfWork
from app.data.repositories.snowflake_records import SnowflakeRecordRepository
from app.models import (
    ManuscriptProposalCreate,
    ProjectCreate,
    SceneContractCreate,
    SceneContractUpdate,
    SnowflakeRecordRevisionCreate,
)
from app.services.backup_service import ProjectBackupService


class SceneSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "app.db"
        self.store = SQLiteWritingDataStore(self.path)
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Source", premise="A gate opens.")
        )
        self.scene = self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=1, title="Gate")
        )
        self.revision = self.record(self.project.id)

    def record(self, project_id, record_id="opening"):
        # This repository test supplies a reviewed record; workflow acceptance is
        # covered separately by compiler tests.
        record = self.store.create_snowflake_record_revision(
            project_id,
            SnowflakeRecordRevisionCreate(
                step_number=8, record_id=record_id, position=1, payload={"title": "Gate"}
            ),
        )
        with SqliteUnitOfWork(self.path) as uow:
            accepted, _ = SnowflakeRecordRepository(uow.connection).decide(
                project_id,
                record.id,
                decision="accepted",
                expected_revision_id="",
                review_reason="test review",
            )
            return accepted

    def bind(self, scene_id=None, project_id=None, revision=None):
        revision = revision or self.revision
        with SqliteUnitOfWork(self.path) as uow:
            uow.scenes.bind_source(
                project_id or self.project.id,
                scene_id or self.scene.id,
                revision.record_id,
                revision.id,
            )

    def test_rename_resequence_and_backup_preserve_stable_identity(self):
        self.assertIsNone(self.store.get_scene_by_source(self.project.id, "opening"))
        self.bind()
        proposal = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(
                scene_id=self.scene.id, title="Author draft", content="The gate opens."
            ),
        )
        self.store.accept_manuscript_proposal(self.project.id, proposal.id)
        history = self.store.list_manuscript_revisions(self.project.id)
        updated = self.store.update_scene_contract(
            self.project.id, self.scene.id, SceneContractUpdate(sequence=4, title="New title")
        )
        self.assertEqual(updated.id, self.scene.id)
        self.assertEqual(updated.plan_version, 2)
        self.assertEqual(updated.source_record_revision_id, self.revision.id)
        self.assertEqual(
            self.store.get_scene_by_source(self.project.id, "opening").id, self.scene.id
        )
        package = ProjectBackupService(self.store, self.root / "projects").export_package(
            self.project.id
        )
        restored = SQLiteWritingDataStore(self.root / "restored.db")
        restored.init()
        ProjectBackupService(restored, self.root / "restored-projects").import_package(package)
        self.assertEqual(restored.get_scene_by_source(self.project.id, "opening"), updated)
        self.assertEqual(restored.list_manuscript_revisions(self.project.id), history)
        self.assertEqual(
            restored.list_manuscript_scenes(self.project.id)[0].scene_id, self.scene.id
        )

    def test_duplicate_source_and_cross_project_source_are_rejected(self):
        self.bind()
        second = self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=2, title="Other")
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.bind(scene_id=second.id)
        other = self.store.create_project(
            ProjectCreate(title="Other project", premise="Other gate")
        )
        other_scene = self.store.create_scene_contract(
            other.id, SceneContractCreate(sequence=1, title="Other gate")
        )
        with self.assertRaises(ValueError):
            self.bind(scene_id=other_scene.id, project_id=other.id)
        with self.assertRaises(sqlite3.IntegrityError):
            with SqliteUnitOfWork(self.path) as uow:
                uow.connection.execute(
                    "UPDATE scene_contracts SET source_record_step=8, source_record_id=?, source_record_revision_id=? WHERE id=?",
                    (self.revision.record_id, self.revision.id, other_scene.id),
                )
        other_record = self.record(other.id)
        self.bind(scene_id=other_scene.id, project_id=other.id, revision=other_record)
        self.assertEqual(self.store.get_scene_by_source(other.id, "opening").id, other_scene.id)

    def test_unlinked_scenes_remain_unlinked_after_restart_and_restore(self):
        self.store.init()
        self.assertEqual(
            self.store.get_scene_contract(self.project.id, self.scene.id).source_record_id, ""
        )
        self.assertIsNone(self.store.get_scene_by_source(self.project.id, self.revision.record_id))
