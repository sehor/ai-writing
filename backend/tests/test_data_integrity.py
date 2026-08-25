from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import (
    CanonEntityCreate,
    ManuscriptChapterCreate,
    MemoryRecordCreate,
    ProjectCreate,
    SceneContractCreate,
    WritebackProposalCreate,
)


class DataIntegrityTests(unittest.TestCase):
    def test_generated_record_ids_are_unique_across_projects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            first = store.create_project(ProjectCreate(title="First", premise="One."))
            second = store.create_project(ProjectCreate(title="Second", premise="Two."))

            first_entity = store.create_canon_entity(
                first.id,
                CanonEntityCreate(entity_type="character", name="Hero"),
            )
            second_entity = store.create_canon_entity(
                second.id,
                CanonEntityCreate(entity_type="character", name="Hero"),
            )
            first_chapter = store.create_manuscript_chapter(
                first.id,
                ManuscriptChapterCreate(sequence=1, title="Opening"),
            )
            second_chapter = store.create_manuscript_chapter(
                second.id,
                ManuscriptChapterCreate(sequence=1, title="Opening"),
            )
            first_scene = store.create_scene_contract(
                first.id,
                SceneContractCreate(
                    chapter_id=first_chapter.id,
                    sequence=1,
                    title="Arrival",
                ),
            )
            second_scene = store.create_scene_contract(
                second.id,
                SceneContractCreate(
                    chapter_id=second_chapter.id,
                    sequence=1,
                    title="Arrival",
                ),
            )
            first_memory = store.create_memory_record(
                first.id,
                MemoryRecordCreate(
                    record_type="voice_sample",
                    title="Hero Voice",
                    content="Quiet.",
                ),
            )
            second_memory = store.create_memory_record(
                second.id,
                MemoryRecordCreate(
                    record_type="voice_sample",
                    title="Hero Voice",
                    content="Quiet.",
                ),
            )

            self.assertNotEqual(first_entity.id, second_entity.id)
            self.assertNotEqual(first_chapter.id, second_chapter.id)
            self.assertNotEqual(first_scene.id, second_scene.id)
            self.assertNotEqual(first_memory.id, second_memory.id)

    def test_accepted_writeback_cannot_return_to_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Review", premise="One."))
            proposal = store.create_writeback_proposal(
                project.id,
                WritebackProposalCreate(
                    target="memory_record",
                    title="Voice",
                    payload={
                        "record_type": "voice_sample",
                        "title": "Voice",
                        "content": "Quiet.",
                    },
                ),
            )

            accepted = store.update_writeback_proposal_status(
                project.id, proposal.id, "accepted"
            )

            self.assertEqual(accepted.status, "accepted")
            with self.assertRaises(ValueError):
                store.update_writeback_proposal_status(
                    project.id, proposal.id, "rejected"
                )
            self.assertEqual(
                store.get_writeback_proposal(project.id, proposal.id).status,
                "accepted",
            )
            self.assertEqual(len(store.list_memory_records(project.id)), 1)

    def test_writeback_acceptance_rolls_back_applied_record_when_status_update_fails(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Atomic", premise="One."))
            proposal = store.create_writeback_proposal(
                project.id,
                WritebackProposalCreate(
                    target="memory_record",
                    title="Voice",
                    payload={
                        "record_type": "voice_sample",
                        "title": "Voice",
                        "content": "Quiet.",
                    },
                ),
            )
            with store.connect() as connection:
                connection.execute(
                    """
                    CREATE TRIGGER reject_writeback_acceptance
                    BEFORE UPDATE OF status ON writeback_proposals
                    WHEN NEW.status = 'accepted'
                    BEGIN
                        SELECT RAISE(ABORT, 'forced status failure');
                    END;
                    """
                )

            with self.assertRaises(sqlite3.IntegrityError):
                store.update_writeback_proposal_status(
                    project.id, proposal.id, "accepted"
                )

            self.assertEqual(store.list_memory_records(project.id), [])
            self.assertEqual(
                store.get_writeback_proposal(project.id, proposal.id).status,
                "pending_review",
            )

    def test_writeback_route_returns_conflict_after_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Route", premise="One."))
            proposal = store.create_writeback_proposal(
                project.id,
                WritebackProposalCreate(
                    target="memory_record",
                    title="Voice",
                    payload={
                        "record_type": "voice_sample",
                        "title": "Voice",
                        "content": "Quiet.",
                    },
                ),
            )
            store.update_writeback_proposal_status(
                project.id, proposal.id, "accepted"
            )
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    response = client.put(
                        f"/api/projects/{project.id}/writeback/proposals/{proposal.id}/status",
                        json={"status": "rejected"},
                    )
            finally:
                app.dependency_overrides.clear()

            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                store.get_writeback_proposal(project.id, proposal.id).status,
                "accepted",
            )

    def test_scene_route_rejects_chapter_from_outside_the_project(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Scene", premise="One."))
            other_project = store.create_project(
                ProjectCreate(title="Other Scene", premise="Two.")
            )
            other_chapter = store.create_manuscript_chapter(
                other_project.id,
                ManuscriptChapterCreate(sequence=1, title="Other Chapter"),
            )
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    response = client.post(
                        f"/api/projects/{project.id}/scene-contracts",
                        json={
                            "chapter_id": other_chapter.id,
                            "sequence": 1,
                            "title": "Lost Scene",
                        },
                    )
            finally:
                app.dependency_overrides.clear()

            self.assertEqual(response.status_code, 422)
            self.assertEqual(store.list_scene_contracts(project.id), [])


if __name__ == "__main__":
    unittest.main()
