from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.agents.writing_workflow import LocalDraftWritingWorkflow
from app.data import SQLiteWritingDataStore, get_data_store
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import (
    WikiContextQuery,
    WikiContextResult,
    WikiIngestionResult,
    WikiInsightQuery,
    WikiInsightResult,
    WikiSourceDocument,
)
from app.main import app
from app.outbox.service import OutboxService
from app.routers.snowflake import SNOWFLAKE_STEPS, get_writing_workflow


class FlakyLlmWiki:
    """Ingest fails a configurable number of times, then recovers."""

    def __init__(self, ingest_failures: int = 1) -> None:
        self.remaining_failures = ingest_failures
        self.documents: list[WikiSourceDocument] = []

    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError("simulated llm wiki outage")
        self.documents.append(document)
        return WikiIngestionResult(status="stored", source_ref=document.source_ref)

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        return WikiContextResult(summary="stub", evidence=[], constraints=[])

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        return WikiInsightResult(summary="stub", insights=[])


class OutboxAcceptanceTests(unittest.TestCase):
    def _install(self, temp_dir: str, wiki: FlakyLlmWiki) -> SQLiteWritingDataStore:
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        app.dependency_overrides[get_data_store] = lambda: store
        app.dependency_overrides[get_llm_wiki] = lambda: wiki
        app.dependency_overrides[get_writing_workflow] = lambda: LocalDraftWritingWorkflow(
            store, SNOWFLAKE_STEPS, wiki
        )
        return store

    def _create_scene_and_proposal(self, client: TestClient, project_id: str) -> str:
        scene_response = client.post(
            f"/api/projects/{project_id}/scene-contracts",
            json={
                "sequence": 1,
                "title": "Archive Threshold",
                "pov": "Mira",
                "goal": "Enter the archive.",
                "conflict": "The map refuses the door.",
                "turning_point": "The map redraws itself.",
                "source_artifact_step": 8,
            },
        )
        self.assertEqual(scene_response.status_code, 201)
        scene_id = scene_response.json()["id"]
        proposal_response = client.post(
            f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene_id}"
        )
        self.assertEqual(proposal_response.status_code, 201)
        return proposal_response.json()["id"]

    def test_manuscript_accept_survives_wiki_outage_and_retry_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = FlakyLlmWiki(ingest_failures=1)
            store = self._install(temp_dir, wiki)
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={"title": "Outbox Novel", "premise": "Trust the outbox."},
                    ).json()["id"]
                    proposal_id = self._create_scene_and_proposal(client, project_id)

                    accepted = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal_id}/status",
                        json={"status": "accepted"},
                    )

                    # Core data is saved and reported as such, not a 500.
                    self.assertEqual(accepted.status_code, 200)
                    self.assertEqual(accepted.headers.get("X-Wiki-Index-Status"), "failed")
                    self.assertIn("Core data saved", accepted.headers["X-Wiki-Index-Message"])
                    revisions = store.list_manuscript_revisions(project_id)
                    self.assertEqual(len(revisions), 1)
                    self.assertEqual(len(wiki.documents), 0)

                    # The failed job is visible and carries the error.
                    jobs = store.list_outbox_jobs(project_id, job_status="failed")
                    self.assertEqual(len(jobs), 1)
                    job = jobs[0]
                    self.assertGreaterEqual(job.attempt_count, 1)
                    self.assertIn("RuntimeError", job.last_error)

                    # Recovery: retry marks the job succeeded without side effects.
                    wiki.remaining_failures = 0
                    retried = client.post(f"/api/projects/{project_id}/outbox-jobs/{job.id}/retry")
                    self.assertEqual(retried.status_code, 200)
                    self.assertEqual(retried.json()["status"], "succeeded")
                    self.assertEqual(len(wiki.documents), 1)
                    self.assertEqual(
                        wiki.documents[0].source_ref, f"manuscript_revision:{revisions[0].id}"
                    )
                    self.assertEqual(len(store.list_manuscript_revisions(project_id)), 1)

                    # Retrying a succeeded job is rejected as a conflict.
                    conflict = client.post(f"/api/projects/{project_id}/outbox-jobs/{job.id}/retry")
                    self.assertEqual(conflict.status_code, 409)

                    # Re-dispatching finds nothing pending: no duplicate ingest.
                    outbox = OutboxService(data_store=store, wiki=wiki)
                    processed_again = outbox.process_pending(project_id)
                    self.assertEqual(processed_again, [])
                    self.assertEqual(len(wiki.documents), 1)
            finally:
                app.dependency_overrides.clear()

    def test_snowflake_save_enqueues_index_job_atomically(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = FlakyLlmWiki(ingest_failures=10**6)
            store = self._install(temp_dir, wiki)
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={"title": "Snowflake Outbox", "premise": "Steps survive."},
                    ).json()["id"]

                    saved = client.put(
                        f"/api/projects/{project_id}/snowflake/artifacts/1",
                        json={"content": "Mira must map the archive."},
                    )

                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(saved.headers.get("X-Wiki-Index-Status"), "failed")

                    # Artifact and project progress are committed despite failure.
                    artifact = store.get_snowflake_artifact(project_id, 1)
                    self.assertIsNotNone(artifact)
                    self.assertIn("archive", artifact.content)
                    project = store.get_project(project_id)
                    self.assertEqual(project.current_step, 2)

                    failed_jobs = store.list_outbox_jobs(project_id, job_status="failed")
                    self.assertEqual(len(failed_jobs), 1)
                    payload = failed_jobs[0].payload
                    self.assertEqual(payload["source_kind"], "snowflake_artifact")
                    self.assertEqual(payload["knowledge_class"], "planned")

                    wiki.remaining_failures = 0
                    retried = client.post(
                        f"/api/projects/{project_id}/outbox-jobs/{failed_jobs[0].id}/retry"
                    )
                    self.assertEqual(retried.status_code, 200)
                    self.assertEqual(retried.json()["status"], "succeeded")
                    self.assertEqual(len(wiki.documents), 1)
                    self.assertEqual(wiki.documents[0].content, "Mira must map the archive.")

                    # A fresh save creates a NEW index job instead of being
                    # deduplicated away by the previous event's key.
                    second = client.put(
                        f"/api/projects/{project_id}/snowflake/artifacts/1",
                        json={"content": "Revised sentence for step one."},
                    )
                    self.assertEqual(second.status_code, 200)
                    pending_or_done = store.list_outbox_jobs(project_id)
                    self.assertEqual(len(pending_or_done), 2)
                    self.assertEqual(len(wiki.documents), 2)
            finally:
                app.dependency_overrides.clear()

    def test_insert_outbox_job_is_idempotent_on_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            with store.connect() as connection:
                first = store.insert_outbox_job(
                    connection,
                    project_id="demo-novel",
                    job_type="llm_wiki_ingest",
                    aggregate_type="manuscript_revision",
                    aggregate_id="rev-1",
                    payload={"hello": "world"},
                    idempotency_key="llm_wiki_ingest:manuscript_revision:rev-1",
                )
                second = store.insert_outbox_job(
                    connection,
                    project_id="demo-novel",
                    job_type="llm_wiki_ingest",
                    aggregate_type="manuscript_revision",
                    aggregate_id="rev-1",
                    payload={"hello": "world"},
                    idempotency_key="llm_wiki_ingest:manuscript_revision:rev-1",
                )
            self.assertEqual(first, second)
            self.assertEqual(len(store.list_outbox_jobs("demo-novel")), 1)


if __name__ == "__main__":
    unittest.main()
