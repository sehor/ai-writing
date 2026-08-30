import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from _polling import wait_until
from app.cognition.registry import get_cognition_registry
from app.data import SQLiteWritingDataStore, get_data_store
from app.integrations.llmwiki_clp import CLP_BASE_URL_ENV, CLP_TIMEOUT_ENV
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import WikiIngestionResult
from app.main import app
from app.models import ManuscriptProposalCreate, ProjectCreate, SceneContractCreate
from app.outbox.dispatcher import get_outbox_dispatcher


class FailingWakeDispatcher:
    def wake(self) -> None:
        raise RuntimeError("derived pipeline wake failed")


class NoopWiki:
    def ingest(self, document) -> WikiIngestionResult:
        return WikiIngestionResult(status="stored", source_ref=document.source_ref)


class UnavailableGraphModule:
    def analyze(self, snapshot):
        raise RuntimeError("advisory graph unavailable")


class UnavailableCognition:
    graph_module = UnavailableGraphModule()

    def prepare_context(self, snapshot, scope):
        raise RuntimeError("cognition context unavailable")

    def ingest_committed_content(self, snapshot, event):
        raise RuntimeError("cognition writeback unavailable")


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

    def test_advisory_graph_and_cognition_failure_do_not_block_authoring(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Graph Failure Isolation",
                    premise="Advisory components cannot own authoritative availability.",
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

            unavailable = UnavailableCognition()
            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_llm_wiki] = lambda: NoopWiki()
            app.dependency_overrides[get_cognition_registry] = lambda: unavailable
            try:
                with TestClient(app, raise_server_exceptions=False) as client:
                    graph = client.get(f"/api/projects/{project.id}/graph/analysis")
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

                    wait_until(
                        lambda: all(
                            job.status in {"succeeded", "failed"}
                            for job in store.list_outbox_jobs(project.id)
                        ),
                        timeout_seconds=20,
                        message="cognition failures to settle without blocking authoring",
                    )
            finally:
                app.dependency_overrides.clear()

            self.assertEqual(graph.status_code, 500)
            self.assertEqual(accept.status_code, 200)
            self.assertEqual(manual_save.status_code, 200)
            self.assertEqual(restore.status_code, 200)
            self.assertEqual(read_scenes.status_code, 200)
            self.assertEqual(read_revisions.status_code, 200)
            self.assertEqual(export.status_code, 200)

            revisions = store.list_manuscript_revisions(project.id)
            self.assertEqual(len(revisions), 3)
            self.assertEqual(read_scenes.json()[0]["content"], "ORIGINAL_ACCEPTED_PROSE")
            self.assertIn("ORIGINAL_ACCEPTED_PROSE", export.json()["content"])

            jobs = store.list_outbox_jobs(project.id)
            cognition_jobs = [job for job in jobs if job.job_type == "writeback_analysis"]
            other_jobs = [job for job in jobs if job.job_type != "writeback_analysis"]
            self.assertEqual(len(cognition_jobs), len(revisions))
            self.assertTrue(all(job.status == "failed" for job in cognition_jobs))
            self.assertTrue(
                all("cognition writeback unavailable" in job.last_error for job in cognition_jobs)
            )
            self.assertTrue(all(job.status == "succeeded" for job in other_jobs))

    def test_malformed_clp_configuration_isolated_to_retryable_clp_jobs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Malformed CLP Isolation",
                    premise="Optional compiler configuration cannot own authoring availability.",
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
            app.dependency_overrides[get_llm_wiki] = lambda: NoopWiki()
            malformed_clp = {
                CLP_BASE_URL_ENV: "http://127.0.0.1:43117",
                CLP_TIMEOUT_ENV: "not-a-number",
            }
            try:
                with patch.dict(os.environ, malformed_clp, clear=False):
                    with TestClient(app, raise_server_exceptions=False) as client:
                        project_read = client.get("/api/projects")
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
                        read_revisions = client.get(
                            f"/api/projects/{project.id}/manuscript/revisions"
                        )
                        export = client.get(f"/api/projects/{project.id}/manuscript/export")

                        wait_until(
                            lambda: all(
                                job.status in {"succeeded", "failed"}
                                for job in store.list_outbox_jobs(project.id)
                            ),
                            timeout_seconds=20,
                            message="malformed CLP jobs to fail without blocking other derived jobs",
                        )
                        first_clp_job = next(
                            job
                            for job in store.list_outbox_jobs(project.id)
                            if job.job_type == "clp_extraction"
                            and job.aggregate_id == first_revision.id
                        )
                        retry = client.post(
                            f"/api/projects/{project.id}/outbox-jobs/{first_clp_job.id}/retry"
                        )
            finally:
                app.dependency_overrides.clear()

            self.assertEqual(project_read.status_code, 200)
            self.assertIn(project.id, {item["id"] for item in project_read.json()})
            self.assertEqual(accept.status_code, 200)
            self.assertEqual(manual_save.status_code, 200)
            self.assertEqual(restore.status_code, 200)
            self.assertEqual(read_scenes.status_code, 200)
            self.assertEqual(read_revisions.status_code, 200)
            self.assertEqual(export.status_code, 200)
            self.assertEqual(retry.status_code, 200)

            revisions = store.list_manuscript_revisions(project.id)
            self.assertEqual(len(revisions), 3)
            self.assertEqual(read_scenes.json()[0]["content"], "ORIGINAL_ACCEPTED_PROSE")
            self.assertIn("ORIGINAL_ACCEPTED_PROSE", export.json()["content"])

            jobs = store.list_outbox_jobs(project.id)
            clp_jobs = [job for job in jobs if job.job_type == "clp_extraction"]
            non_clp_jobs = [job for job in jobs if job.job_type != "clp_extraction"]
            self.assertEqual(len(clp_jobs), len(revisions))
            self.assertTrue(all(job.status == "failed" for job in clp_jobs))
            self.assertTrue(all(job.status == "succeeded" for job in non_clp_jobs))
            self.assertTrue(
                {revision.id for revision in revisions} <= {job.aggregate_id for job in clp_jobs}
            )

            retried_job = store.get_outbox_job(project.id, first_clp_job.id)
            self.assertEqual(retried_job.status, "failed")
            self.assertEqual(retried_job.attempt_count, 2)
            self.assertIn(CLP_TIMEOUT_ENV, retried_job.last_error)

            clp_runs = [
                run
                for run in store.list_analysis_runs(project.id)
                if run.processor == "llmwiki_clp"
            ]
            self.assertTrue(clp_runs)
            self.assertTrue(all(run.status == "failed" for run in clp_runs))
            self.assertTrue(
                all(CLP_TIMEOUT_ENV in run.result_json.get("error", "") for run in clp_runs)
            )


if __name__ == "__main__":
    unittest.main()
