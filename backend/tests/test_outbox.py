from collections.abc import Callable
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
from _polling import wait_until


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
                    # P1-03: the response returns before any handler runs; the
                    # background dispatcher produces the failure on its own.
                    self.assertEqual(accepted.status_code, 200)
                    self.assertNotIn("X-Wiki-Index-Status", accepted.headers)
                    jobs = wait_until(
                        lambda: store.list_outbox_jobs(project_id, job_status="failed"),
                        timeout_seconds=20,
                        message="wiki ingest job to fail in the background dispatcher",
                    )
                    revisions = store.list_manuscript_revisions(project_id)
                    self.assertEqual(len(revisions), 1)
                    self.assertEqual(len(wiki.documents), 0)

                    # The failed job is visible and carries the error.
                    self.assertEqual(len(jobs), 1)
                    job = jobs[0]
                    self.assertGreaterEqual(job.attempt_count, 1)
                    self.assertIn("RuntimeError", job.last_error)

                    # Retry only queues work; the background dispatcher completes it.
                    wiki.remaining_failures = 0
                    retried = client.post(f"/api/projects/{project_id}/outbox-jobs/{job.id}/retry")
                    self.assertEqual(retried.status_code, 202)
                    self.assertEqual(retried.json()["status"], "pending")
                    wait_until(
                        lambda: store.get_outbox_job(project_id, job.id).status == "succeeded",
                        timeout_seconds=20,
                        message="retried wiki job to finish",
                    )
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
                    # P1-03: the artifact save no longer runs the handler
                    # inline; the dispatcher fails it in the background.
                    failed_jobs = wait_until(
                        lambda: store.list_outbox_jobs(project_id, job_status="failed"),
                        timeout_seconds=20,
                        message="snowflake index job to fail in the background dispatcher",
                    )
                    # Artifact and project progress are committed despite failure.
                    artifact = store.get_snowflake_artifact(project_id, 1)
                    self.assertIsNotNone(artifact)
                    self.assertIn("archive", artifact.content)
                    project = store.get_project(project_id)
                    self.assertEqual(project.current_step, 2)

                    self.assertEqual(len(failed_jobs), 1)
                    payload = failed_jobs[0].payload
                    self.assertEqual(payload["source_kind"], "snowflake_artifact")
                    self.assertEqual(payload["knowledge_class"], "planned")

                    wiki.remaining_failures = 0
                    retried = client.post(
                        f"/api/projects/{project_id}/outbox-jobs/{failed_jobs[0].id}/retry"
                    )
                    self.assertEqual(retried.status_code, 202)
                    self.assertEqual(retried.json()["status"], "pending")
                    wait_until(
                        lambda: (
                            store.get_outbox_job(project_id, failed_jobs[0].id).status
                            == "succeeded"
                        ),
                        timeout_seconds=20,
                        message="retried snowflake job to finish",
                    )
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
                    wait_until(
                        lambda: len(wiki.documents) == 2,
                        timeout_seconds=20,
                        message="the second background ingest to land",
                    )
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


class CountingLlmWiki:
    """Never fails; records ingest calls so double execution is observable."""

    def __init__(self) -> None:
        self.documents: list[WikiSourceDocument] = []

    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        self.documents.append(document)
        return WikiIngestionResult(status="stored", source_ref=document.source_ref)

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        return WikiContextResult(summary="stub", evidence=[], constraints=[])

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        return WikiInsightResult(summary="stub", insights=[])


def _wiki_ingest_payload(project_id: str, revision_id: str) -> dict:
    """Minimal payload that passes WikiSourceDocument validation."""
    return {
        "project_id": project_id,
        "source_kind": "manuscript_revision",
        "source_ref": f"manuscript_revision:{revision_id}",
        "title": "Chapter One",
        "content": "Mira opens the archive door.",
        "snowflake_step": 10,
        "artifact_type": "manuscript",
        "knowledge_class": "observed",
    }


class RacingDataStore:
    """Proxy that runs a hook just before an outbox CAS call.

    The hook forces the dispatcher race deterministically: another service
    fully processes the same job first, and then this caller's claim/retry
    attempt must lose the compare-and-set instead of re-running the handler.
    """

    def __init__(self, inner: object, hooks: dict[str, Callable[[], None]]):
        self._inner = inner
        self._hooks = hooks

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def claim_outbox_job(self, *args, **kwargs):
        hook = self._hooks.get("claim_outbox_job")
        if hook is not None:
            hook()
        return self._inner.claim_outbox_job(*args, **kwargs)

    def reset_failed_outbox_job(self, *args, **kwargs):
        hook = self._hooks.get("reset_failed_outbox_job")
        if hook is not None:
            hook()
        return self._inner.reset_failed_outbox_job(*args, **kwargs)


class OutboxClaimRecoveryTests(unittest.TestCase):
    """P1-02: atomic claim, crash recovery, stale-processing recovery."""

    PROJECT_ID = "recovery-novel"

    def _store(self, temp_dir: str) -> SQLiteWritingDataStore:
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        return store

    def _insert_pending_job(self, store: SQLiteWritingDataStore) -> str:
        with store.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, title, premise, current_step)"
                " VALUES (?, 'Recovery Novel', 'Jobs survive restarts.', 1)",
                (self.PROJECT_ID,),
            )
            return store.insert_outbox_job(
                connection,
                project_id=self.PROJECT_ID,
                job_type="llm_wiki_ingest",
                aggregate_type="manuscript_revision",
                aggregate_id="rev-1",
                payload=_wiki_ingest_payload(self.PROJECT_ID, "rev-1"),
                idempotency_key="llm_wiki_ingest:manuscript_revision:rev-1",
            )

    def test_claim_is_single_winner_across_connections(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store_a = self._store(temp_dir)
            job_id = self._insert_pending_job(store_a)
            store_b = SQLiteWritingDataStore(store_a.database_path)

            first = store_a.claim_outbox_job(self.PROJECT_ID, job_id)
            second = store_b.claim_outbox_job(self.PROJECT_ID, job_id)

            self.assertIsNotNone(first)
            self.assertEqual(first.status, "processing")
            self.assertEqual(first.attempt_count, 1)
            self.assertNotEqual(first.processing_started_at, "")
            # A concurrent dispatcher must not win the same pending job.
            self.assertIsNone(second)

    def test_terminal_transition_requires_processing_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            job_id = self._insert_pending_job(store)

            # A pending job cannot be finalized without being claimed.
            self.assertIsNone(store.complete_outbox_job(self.PROJECT_ID, job_id, succeeded=True))

            store.claim_outbox_job(self.PROJECT_ID, job_id)
            done = store.complete_outbox_job(
                self.PROJECT_ID, job_id, succeeded=False, error="RuntimeError: boom"
            )
            self.assertEqual(done.status, "failed")
            self.assertIn("boom", done.last_error)
            self.assertNotEqual(done.completed_at, "")
            self.assertEqual(done.processing_started_at, "")

            # Terminal 'failed' rejects claim/complete; only the CAS retry
            # gate may move it back to pending.
            self.assertIsNone(store.claim_outbox_job(self.PROJECT_ID, job_id))
            self.assertIsNone(store.complete_outbox_job(self.PROJECT_ID, job_id, succeeded=True))
            retried = store.reset_failed_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(retried.status, "pending")

    def test_second_dispatcher_skips_already_claimed_job(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store_a = self._store(temp_dir)
            job_id = self._insert_pending_job(store_a)
            wiki_a = CountingLlmWiki()
            wiki_b = CountingLlmWiki()

            # Dispatcher B shares only the database, not process state.
            service_b = OutboxService(
                data_store=SQLiteWritingDataStore(store_a.database_path), wiki=wiki_b
            )
            racing_store = RacingDataStore(
                store_a, {"claim_outbox_job": lambda: service_b.process_pending(self.PROJECT_ID)}
            )
            service_a = OutboxService(data_store=racing_store, wiki=wiki_a)

            service_a.process_pending(self.PROJECT_ID)

            # B won the claim and executed; A must not run it again.
            self.assertEqual(len(wiki_b.documents), 1)
            self.assertEqual(wiki_a.documents, [])
            final = store_a.get_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(final.status, "succeeded")
            self.assertEqual(final.attempt_count, 1)

    def test_succeeded_jobs_are_never_reexecuted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            job_id = self._insert_pending_job(store)
            wiki = CountingLlmWiki()
            service = OutboxService(data_store=store, wiki=wiki)

            service.process_pending(self.PROJECT_ID)

            self.assertEqual(service.process_pending(self.PROJECT_ID), [])
            self.assertEqual(service.resume_pending_jobs(), [])
            self.assertIsNone(store.claim_outbox_job(self.PROJECT_ID, job_id))
            self.assertIsNone(store.complete_outbox_job(self.PROJECT_ID, job_id, succeeded=True))
            self.assertEqual(len(wiki.documents), 1)
            self.assertEqual(store.get_outbox_job(self.PROJECT_ID, job_id).attempt_count, 1)

    def test_retry_race_runs_handler_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            job_id = self._insert_pending_job(store)

            failing = FlakyLlmWiki(ingest_failures=1)
            OutboxService(data_store=store, wiki=failing).process_pending(self.PROJECT_ID)
            failed = store.get_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(failed.status, "failed")

            wiki_a = CountingLlmWiki()
            wiki_b = CountingLlmWiki()
            service_b = OutboxService(
                data_store=SQLiteWritingDataStore(store.database_path), wiki=wiki_b
            )
            racing_store = RacingDataStore(
                store,
                {"reset_failed_outbox_job": lambda: service_b.retry(self.PROJECT_ID, job_id)},
            )
            with self.assertRaises(ValueError):
                OutboxService(data_store=racing_store, wiki=wiki_a).retry(self.PROJECT_ID, job_id)

            # B queued the retry, A lost the CAS race; neither ran a handler inline.
            self.assertEqual(wiki_b.documents, [])
            self.assertEqual(wiki_a.documents, [])
            self.assertEqual(store.get_outbox_job(self.PROJECT_ID, job_id).status, "pending")
            service_b.process_pending(self.PROJECT_ID)
            self.assertEqual(len(wiki_b.documents), 1)
            final = store.get_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(final.status, "succeeded")
            self.assertEqual(final.attempt_count, 2)
            with self.assertRaises(ValueError):
                service_b.retry(self.PROJECT_ID, job_id)

    def test_pending_job_survives_restart_and_is_resumed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            job_id = self._insert_pending_job(store)

            # Simulated crash: nothing dispatched before the restart.
            wiki = CountingLlmWiki()
            restarted = OutboxService(data_store=self._store(temp_dir), wiki=wiki)
            resumed = restarted.resume_pending_jobs()

            self.assertEqual([job.id for job in resumed], [job_id])
            self.assertEqual(resumed[0].status, "succeeded")
            self.assertEqual(len(wiki.documents), 1)

    def test_stale_processing_job_is_recovered_and_rerun(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            job_id = self._insert_pending_job(store)

            claimed = store.claim_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(claimed.status, "processing")
            # Worker died mid-handler: backdate the lease stamp beyond any lease.
            with store.connect() as connection:
                connection.execute(
                    "UPDATE outbox_jobs SET processing_started_at = ? WHERE id = ?",
                    ("2000-01-01T00:00:00+00:00", job_id),
                )

            wiki = CountingLlmWiki()
            service = OutboxService(data_store=store, wiki=wiki)
            recovered = service.recover_stale_processing_jobs(lease_seconds=600)

            self.assertEqual([job.id for job in recovered], [job_id])
            self.assertEqual(recovered[0].status, "pending")
            finished = service.resume_pending_jobs()
            self.assertEqual(finished[0].status, "succeeded")
            self.assertEqual(len(wiki.documents), 1)
            final = store.get_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(final.attempt_count, 2)

    def test_fresh_processing_job_is_not_stolen(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            job_id = self._insert_pending_job(store)

            claimed = store.claim_outbox_job(self.PROJECT_ID, job_id)
            wiki = CountingLlmWiki()
            service = OutboxService(data_store=store, wiki=wiki)

            recovered = service.recover_stale_processing_jobs(lease_seconds=3600)

            self.assertEqual(recovered, [])
            still = store.get_outbox_job(self.PROJECT_ID, job_id)
            self.assertEqual(still.status, "processing")
            self.assertEqual(still.id, claimed.id)
            self.assertEqual(service.resume_pending_jobs(), [])
            self.assertEqual(wiki.documents, [])


if __name__ == "__main__":
    unittest.main()
