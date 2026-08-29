"""P1-03 regressions: the app-owned outbox dispatcher runs jobs off the request path.

The HTTP mutation must only commit core data and signal the dispatcher; the
handlers run in a background loop inside the app process, jobs left behind by
a crash are consumed on startup, and every scheduled job settles to a
terminal status after the mutation has already returned.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from fastapi.testclient import TestClient

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
from app.outbox.dispatcher import OutboxDispatcher, build_app_outbox_dispatcher
from app.outbox.service import OutboxService
from _polling import wait_until


class SlowLlmWiki:
    """Ingest sleeps so request-latency decoupling becomes measurable."""

    def __init__(self, ingest_delay_seconds: float) -> None:
        self.ingest_delay_seconds = ingest_delay_seconds
        self.documents: list[WikiSourceDocument] = []

    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        time.sleep(self.ingest_delay_seconds)
        self.documents.append(document)
        return WikiIngestionResult(status="stored", source_ref=document.source_ref)

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        return WikiContextResult(summary="stub", evidence=[], constraints=[])

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        return WikiInsightResult(summary="stub", insights=[])


class RecordingLlmWiki:
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


def _insert_pending_wiki_job(store: SQLiteWritingDataStore, project_id: str) -> str:
    with store.connect() as connection:
        connection.execute(
            "INSERT INTO projects (id, title, premise, current_step)"
            " VALUES (?, 'Recovery Novel', 'Jobs survive restarts.', 1)",
            (project_id,),
        )
        return store.insert_outbox_job(
            connection,
            project_id=project_id,
            job_type="llm_wiki_ingest",
            aggregate_type="manuscript_revision",
            aggregate_id="rev-1",
            payload=_wiki_ingest_payload(project_id, "rev-1"),
            idempotency_key=f"llm_wiki_ingest:manuscript_revision:{project_id}-rev-1",
        )


class DispatcherLifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Unit-level behaviour of the loop itself, without any HTTP stack."""

    async def test_stop_before_start_is_a_safe_noop(self) -> None:
        dispatcher = OutboxDispatcher(service=object())
        await dispatcher.stop()
        self.assertFalse(dispatcher.is_running())

    async def test_start_twice_keeps_a_single_loop_task(self) -> None:
        dispatcher = OutboxDispatcher(service=object())
        try:
            dispatcher.start()
            first_task = dispatcher.loop_task()
            dispatcher.start()
            self.assertIs(dispatcher.loop_task(), first_task)
            self.assertTrue(dispatcher.is_running())
        finally:
            await dispatcher.stop()
        self.assertFalse(dispatcher.is_running())
        self.assertTrue(first_task.done())

    async def test_dispatch_once_drains_pending_jobs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            job_id = _insert_pending_wiki_job(store, "drain-novel")
            wiki = RecordingLlmWiki()
            dispatcher = OutboxDispatcher(service=OutboxService(data_store=store, wiki=wiki))

            processed = await dispatcher.dispatch_once()

            self.assertEqual([job.id for job in processed], [job_id])
            self.assertEqual([job.status for job in processed], ["succeeded"])
            self.assertEqual(len(wiki.documents), 1)
            self.assertEqual(store.get_outbox_job("drain-novel", job_id).status, "succeeded")


class DispatcherHttpContractTests(unittest.TestCase):
    """End-to-end through the FastAPI app with its lifespan running."""

    def _install_overrides(self, temp_dir: str, wiki) -> SQLiteWritingDataStore:
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        app.dependency_overrides[get_data_store] = lambda: store
        app.dependency_overrides[get_llm_wiki] = lambda: wiki
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
        proposal_response = client.post(
            f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene_response.json()['id']}"
        )
        self.assertEqual(proposal_response.status_code, 201)
        return proposal_response.json()["id"]

    def test_accept_request_returns_before_slow_handlers_finish(self) -> None:
        """THE P1-03 invariant: handler latency no longer rides the mutation."""
        with TemporaryDirectory() as temp_dir:
            wiki = SlowLlmWiki(ingest_delay_seconds=1.2)
            store = self._install_overrides(temp_dir, wiki)
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={"title": "Latency Novel", "premise": "Do not wait on me."},
                    ).json()["id"]
                    proposal_id = self._create_scene_and_proposal(client, project_id)

                    started = time.perf_counter()
                    accepted = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal_id}/status",
                        json={"status": "accepted"},
                    )
                    elapsed = time.perf_counter() - started

                    # Core data committed; the response no longer pretends the
                    # side effects already ran.
                    self.assertEqual(accepted.status_code, 200)
                    self.assertLess(
                        elapsed,
                        0.7,
                        "acceptance waited for the slow wiki handler inside the request",
                    )
                    self.assertNotIn("X-Wiki-Index-Status", accepted.headers)
                    self.assertNotIn("X-Analysis-Job-Status", accepted.headers)
                    self.assertEqual(len(wiki.documents), 0)

                    # The dispatcher finishes the work after the response.
                    jobs = lambda: store.list_outbox_jobs(project_id)
                    wait_until(
                        lambda: [
                            job.status for job in jobs() if job.job_type == "llm_wiki_ingest"
                        ]
                        == ["succeeded"],
                        timeout_seconds=20,
                        message="wiki ingest job to succeed in the background",
                    )
                    self.assertEqual(len(wiki.documents), 1)
                    self.assertEqual(len(store.list_manuscript_revisions(project_id)), 1)
            finally:
                app.dependency_overrides.clear()

    def test_all_scheduled_jobs_settle_after_the_mutation_returned(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = RecordingLlmWiki()
            store = self._install_overrides(temp_dir, wiki)
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={"title": "Settle Novel", "premise": "Everything converges."},
                    ).json()["id"]
                    proposal_id = self._create_scene_and_proposal(client, project_id)
                    accepted = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal_id}/status",
                        json={"status": "accepted"},
                    )
                    self.assertEqual(accepted.status_code, 200)

                    wait_until(
                        lambda: all(
                            job.status == "succeeded"
                            for job in store.list_outbox_jobs(project_id)
                        ),
                        timeout_seconds=20,
                        message="all four post-commit jobs to succeed",
                    )

                    jobs = sorted(job.job_type for job in store.list_outbox_jobs(project_id))
                    self.assertEqual(
                        jobs,
                        [
                            "clp_extraction",
                            "consistency_analysis",
                            "llm_wiki_ingest",
                            "writeback_analysis",
                        ],
                    )
                    self.assertEqual(len(wiki.documents), 1)

                    # Automatic write-back analysis stays review-only.
                    proposals = store.list_writeback_proposals(project_id)
                    self.assertTrue(proposals)
                    self.assertTrue(all(item.status == "pending_review" for item in proposals))
            finally:
                app.dependency_overrides.clear()

    def test_leftover_pending_job_is_consumed_on_startup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            job_id = _insert_pending_wiki_job(store, "crash-novel")
            wiki = RecordingLlmWiki()
            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_llm_wiki] = lambda: wiki
            try:
                # No HTTP mutation ever happens: booting the app alone must
                # resume the pending leftover (P1-02 crash + P1-03 startup).
                with TestClient(app):
                    wait_until(
                        lambda: store.get_outbox_job("crash-novel", job_id).status
                        == "succeeded",
                        timeout_seconds=20,
                        message="leftover pending job to be consumed on startup",
                    )
                self.assertEqual(len(wiki.documents), 1)
            finally:
                app.dependency_overrides.clear()

    def test_stale_processing_job_is_recovered_on_startup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            job_id = _insert_pending_wiki_job(store, "stale-novel")
            claimed = store.claim_outbox_job("stale-novel", job_id)
            self.assertEqual(claimed.status, "processing")
            # Worker died mid-handler: backdate the lease stamp beyond any lease.
            with store.connect() as connection:
                connection.execute(
                    "UPDATE outbox_jobs SET processing_started_at = ? WHERE id = ?",
                    ("2000-01-01T00:00:00+00:00", job_id),
                )

            wiki = RecordingLlmWiki()
            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_llm_wiki] = lambda: wiki
            try:
                with TestClient(app):
                    wait_until(
                        lambda: store.get_outbox_job("stale-novel", job_id).status
                        == "succeeded",
                        timeout_seconds=20,
                        message="stale processing job to be recovered and finished",
                    )
                final = store.get_outbox_job("stale-novel", job_id)
                self.assertEqual(final.attempt_count, 2)
                self.assertEqual(len(wiki.documents), 1)
            finally:
                app.dependency_overrides.clear()

    def test_build_app_outbox_dispatcher_honours_dependency_overrides(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            wiki = RecordingLlmWiki()
            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_llm_wiki] = lambda: wiki
            try:
                dispatcher = build_app_outbox_dispatcher(app)
                self.assertIs(dispatcher.service.data_store, store)
                self.assertIs(dispatcher.service.wiki, wiki)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
