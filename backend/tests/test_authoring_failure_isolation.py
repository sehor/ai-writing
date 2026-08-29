from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import ManuscriptProposalCreate, ProjectCreate, SceneContractCreate
from app.outbox.dispatcher import get_outbox_dispatcher


class FailingWakeDispatcher:
    def wake(self) -> None:
        raise RuntimeError("derived pipeline wake failed")


class AuthoringFailureIsolationTests(unittest.TestCase):
    def test_committed_authoring_survives_post_commit_dispatcher_wake_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Failure Isolation",
                    premise="Derived analysis cannot block committed authoring.",
                )
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=1,
                    title="Archive Threshold",
                    pov="Mira",
                    goal="Enter the archive.",
                    conflict="The lock changes shape.",
                    turning_point="The brass key fits.",
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="1. Archive Threshold",
                    content="ORIGINAL_ACCEPTED_PROSE",
                ),
            )

            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_outbox_dispatcher] = lambda: FailingWakeDispatcher()
            try:
                with TestClient(app, raise_server_exceptions=False) as client:
                    snowflake_save = client.put(
                        f"/api/projects/{project.id}/snowflake/artifacts/1",
                        json={"content": "A cartographer finds a door that redraws itself."},
                    )
                    accept = client.put(
                        f"/api/projects/{project.id}/manuscript/proposals/{proposal.id}/status",
                        json={"status": "accepted"},
                    )
                    first_revision = min(
                        store.list_manuscript_revisions(project.id),
                        key=lambda item: item.version,
                    )
                    manual_save = client.put(
                        f"/api/projects/{project.id}/manuscript/scenes/{scene.id}",
                        json={
                            "title": "Archive Threshold Revised",
                            "content": "MANUAL_EDIT_PROSE",
                        },
                    )
                    restore = client.post(
                        f"/api/projects/{project.id}/manuscript/revisions/{first_revision.id}/restore"
                    )
                    read_scenes = client.get(f"/api/projects/{project.id}/manuscript/scenes")
                    read_revisions = client.get(f"/api/projects/{project.id}/manuscript/revisions")
                    export = client.get(f"/api/projects/{project.id}/manuscript/export")
            finally:
                app.dependency_overrides.clear()

            self.assertEqual(snowflake_save.status_code, 200)
            self.assertEqual(accept.status_code, 200)
            self.assertEqual(manual_save.status_code, 200)
            self.assertEqual(restore.status_code, 200)
            self.assertEqual(read_scenes.status_code, 200)
            self.assertEqual(read_revisions.status_code, 200)
            self.assertEqual(export.status_code, 200)

            saved_artifact = store.get_snowflake_artifact(project.id, 1)
            self.assertIsNotNone(saved_artifact)
            self.assertIn("cartographer", saved_artifact.content)

            accepted_proposal = store.get_manuscript_proposal(project.id, proposal.id)
            self.assertEqual(accepted_proposal.status, "accepted")
            self.assertEqual(len(read_revisions.json()), 3)
            self.assertEqual(read_scenes.json()[0]["content"], "ORIGINAL_ACCEPTED_PROSE")
            self.assertIn("ORIGINAL_ACCEPTED_PROSE", export.json()["content"])

            revision_job_ids = {
                job.aggregate_id
                for job in store.list_outbox_jobs(project.id)
                if job.job_type
                in {
                    "clp_extraction",
                    "consistency_analysis",
                    "llm_wiki_ingest",
                    "writeback_analysis",
                }
            }
            self.assertTrue(
                {revision.id for revision in store.list_manuscript_revisions(project.id)}
                <= revision_job_ids
            )


if __name__ == "__main__":
    unittest.main()
