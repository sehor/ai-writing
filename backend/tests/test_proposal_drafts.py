from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import (
    ManuscriptProposalCreate,
    ManuscriptSceneUpdate,
    ProjectCreate,
    SceneContractCreate,
)
from app.outbox.dispatcher import get_outbox_dispatcher


class ProposalDraftAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteWritingDataStore(Path(self.temp.name) / "app.db")
        self.store.init()
        self.project = self.store.create_project(ProjectCreate(title="Draft", premise="Review it."))
        self.scene = self.store.create_scene_contract(
            self.project.id,
            SceneContractCreate(
                sequence=1,
                title="Door",
                pov="Mira",
                goal="Enter",
                conflict="Locked",
                turning_point="A key",
                source_artifact_step=8,
            ),
        )
        self.proposal = self.new_proposal()
        self.dispatcher = Mock()
        app.dependency_overrides[get_data_store] = lambda: self.store
        app.dependency_overrides[get_outbox_dispatcher] = lambda: self.dispatcher
        self.addCleanup(app.dependency_overrides.clear)
        # No lifespan: these tests inspect the atomic commit before any dispatch.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def new_proposal(self):
        return self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(
                scene_id=self.scene.id,
                title="AI original",
                content="Original AI prose.",
                context="source",
                checklist=[],
            ),
        )

    def accept(self, proposal=None, **overrides):
        body = {
            "title": "Author's title",
            "content": "Author edited prose.",
            "expected_scene_version": 0,
            **overrides,
        }
        return self.client.post(
            f"/api/projects/{self.project.id}/manuscript/proposals/{(proposal or self.proposal).id}/accept",
            json=body,
        )

    def test_edited_acceptance_preserves_original_and_commits_one_revision_and_four_jobs(self):
        response = self.accept()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["content"], "Original AI prose.")
        self.assertEqual(response.json()["status"], "accepted")
        revisions = self.store.list_manuscript_revisions(self.project.id)
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].content, "Author edited prose.")
        self.assertEqual(revisions[0].title, "Author's title")
        self.assertEqual(
            self.store.list_manuscript_scenes(self.project.id)[0].content, revisions[0].content
        )
        jobs = self.store.list_outbox_jobs(self.project.id)
        self.assertEqual(
            {job.job_type for job in jobs},
            {
                "clp_extraction",
                "consistency_analysis",
                "llm_wiki_ingest",
                "writeback_analysis",
            },
        )
        self.assertEqual(len(jobs), 4)
        self.assertTrue(all(job.aggregate_id == revisions[0].id for job in jobs))
        self.assertTrue(all(job.status == "pending" for job in jobs))
        self.assertTrue(self.dispatcher.wake.called)
        # A repeated request is idempotent, even if its body differs.
        self.assertEqual(self.accept(content="Do not replace accepted prose").status_code, 200)
        self.assertEqual(self.store.list_manuscript_revisions(self.project.id), revisions)
        self.assertEqual(self.store.list_outbox_jobs(self.project.id), jobs)

    def test_stale_draft_cannot_overwrite_a_newer_manual_revision(self):
        self.accept()
        pending = self.new_proposal()
        self.store.update_manuscript_scene(
            self.project.id,
            self.scene.id,
            ManuscriptSceneUpdate(
                title="Manual", content="Newer official text", expected_scene_version=1
            ),
        )
        before = self.store.list_manuscript_revisions(self.project.id)
        response = self.accept(pending, expected_scene_version=1)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.store.list_manuscript_revisions(self.project.id), before)
        self.assertEqual(
            self.store.get_manuscript_proposal(self.project.id, pending.id).status, "pending_review"
        )

    def test_invalid_drafts_and_cross_project_acceptance_do_not_mutate(self):
        for body in (
            {"title": "  "},
            {"content": "\n "},
            {"content": "x" * 40001},
            {"expected_scene_version": -1},
        ):
            with self.subTest(body=list(body)):
                self.assertEqual(self.accept(**body).status_code, 422)
        other = self.store.create_project(ProjectCreate(title="Other", premise="Isolated"))
        response = self.client.post(
            f"/api/projects/{other.id}/manuscript/proposals/{self.proposal.id}/accept",
            json={"title": "No", "content": "No", "expected_scene_version": 0},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.store.list_manuscript_revisions(self.project.id), [])
        self.assertEqual(self.store.list_outbox_jobs(self.project.id), [])

    def test_narrative_views_are_read_only_and_project_scoped(self):
        before = self.store.list_outbox_jobs(self.project.id)
        base = f"/api/projects/{self.project.id}/narrative"
        relations = self.client.get(f"{base}/relations")
        self.assertEqual(relations.status_code, 200)
        self.assertEqual(relations.json(), [])
        report = self.client.get(f"{base}/director?scene_id={self.scene.id}")
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(report.json()["scene_id"], self.scene.id)
        self.assertEqual(self.client.get(f"{base}/director?scene_id=foreign").status_code, 404)
        self.assertEqual(
            self.client.get("/api/projects/missing/narrative/relations").status_code, 404
        )
        self.assertEqual(self.store.list_outbox_jobs(self.project.id), before)
