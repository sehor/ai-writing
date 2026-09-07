from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.data.repositories.scene_proposals import (
    SceneProposalReviewedError,
    SceneSequenceConflictError,
)
from app.models import (
    ManuscriptProposalCreate,
    ProjectCreate,
    SceneContractCreate,
    SceneContractUpdate,
    SnowflakeRecordRevisionCreate,
)
from app.services.snowflake_compile_service import SnowflakeCompileService
from app.services.snowflake_service import SnowflakeService
from tests.test_snowflake_compiler import SCENE_RECORDS


class SceneRecordUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteWritingDataStore(Path(self.tmp.name) / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Round trip", premise="A gate opens.")
        )
        self.service = SnowflakeCompileService(self.store)
        self.revisions = {}
        for source in SCENE_RECORDS:
            self.revise(source["record_id"], source["position"], source["payload"])
        initial = self.service.parse_scene_proposals(self.project.id)
        self.store.accept_scene_proposals(self.project.id, [p.id for p in initial.proposals])

    def revise(self, record_id, position=None, payload=None):
        previous = self.revisions.get(record_id)
        revision = self.store.create_snowflake_record_revision(
            self.project.id,
            SnowflakeRecordRevisionCreate(
                step_number=8,
                record_id=record_id,
                position=position or previous.position,
                payload=payload or {**previous.payload, "outcome": "NEW OUTCOME"},
                base_revision_id=previous.id if previous else "",
            ),
        )
        result = self.store.decide_snowflake_record_revision(
            self.project.id,
            revision.id,
            decision="accepted",
            expected_revision_id=previous.id if previous else "",
        )
        self.revisions[record_id] = result.revision

    def dump(self):
        with self.store.connect() as connection:
            return list(connection.iterdump())

    def test_roundtrip_updates_original_scene_preserves_history_and_is_idempotent(self):
        target = self.store.get_scene_by_source(self.project.id, "scene-opening")
        proposal = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(scene_id=target.id, title="Prose", content="Author's prose."),
        )
        self.store.accept_manuscript_proposal(self.project.id, proposal.id)
        history = self.store.list_manuscript_revisions(self.project.id)
        self.revise("scene-opening")
        report = self.service.parse_scene_proposals(self.project.id)
        self.assertEqual(len(report.proposals), 1)
        update = report.proposals[0]
        self.assertEqual(update.operation, "update")
        self.assertEqual(update.target_scene_id, target.id)
        self.assertEqual(update.changes["outcome"]["before"], target.outcome)
        self.assertIn("NEW OUTCOME", update.changes["outcome"]["after"])
        scenes, _ = self.store.accept_scene_proposals(self.project.id, [update.id])
        self.assertEqual(scenes[0].id, target.id)
        self.assertEqual(len(self.store.list_scene_contracts(self.project.id)), 2)
        self.assertEqual(self.store.list_manuscript_revisions(self.project.id), history)
        self.assertLess(scenes[0].manuscript_plan_version, scenes[0].plan_version)
        progress = SnowflakeService(data_store=self.store, llm_wiki=None).manuscript_progress(
            self.project.id
        )
        self.assertGreater(progress.stale_scene_count, 0)
        self.assertFalse(progress.complete)
        before = self.dump()
        self.store.accept_scene_proposals(self.project.id, [update.id])
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.service.parse_scene_proposals(self.project.id).proposals, [])
        self.assertEqual(
            self.service.parse_scene_proposals(self.project.id, force=True).proposals, []
        )

    def test_target_edit_and_newer_source_require_fresh_review(self):
        self.revise("scene-opening")
        update = self.service.parse_scene_proposals(self.project.id).proposals[0]
        target = self.store.get_scene_contract(self.project.id, update.target_scene_id)
        self.store.update_scene_contract(
            self.project.id,
            target.id,
            SceneContractUpdate(**{**target.model_dump(), "title": "Manual title"}),
        )
        before = self.dump()
        with self.assertRaisesRegex(SceneProposalReviewedError, "Target scene plan changed"):
            self.store.accept_scene_proposals(self.project.id, [update.id])
        self.assertEqual(self.dump(), before)
        fresh = self.service.parse_scene_proposals(self.project.id).proposals[0]
        self.assertEqual(fresh.changes["title"]["before"], "Manual title")
        self.revise(
            "scene-opening", payload={**self.revisions["scene-opening"].payload, "outcome": "NEWER"}
        )
        with self.assertRaisesRegex(SceneProposalReviewedError, "Source record changed"):
            self.store.accept_scene_proposals(self.project.id, [fresh.id])

    def test_true_collision_rolls_back_entire_update_batch(self):
        self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=3, title="Unrelated")
        )
        self.revise("scene-opening", position=3)
        self.revise("scene-bargain")
        updates = self.service.parse_scene_proposals(self.project.id).proposals
        before = self.dump()
        with self.assertRaises(SceneSequenceConflictError):
            self.store.accept_scene_proposals(self.project.id, [p.id for p in updates])
        self.assertEqual(self.dump(), before)

    def test_batch_reordering_keeps_both_scene_ids(self):
        original = {
            s.source_record_id: s.id for s in self.store.list_scene_contracts(self.project.id)
        }
        self.revise("scene-opening", position=3)
        self.revise("scene-bargain", position=1)
        self.revise("scene-opening", position=2)
        updates = self.service.parse_scene_proposals(self.project.id).proposals
        self.store.accept_scene_proposals(self.project.id, [p.id for p in updates])
        scenes = self.store.list_scene_contracts(self.project.id)
        self.assertEqual([s.source_record_id for s in scenes], ["scene-bargain", "scene-opening"])
        self.assertEqual({s.source_record_id: s.id for s in scenes}, original)
