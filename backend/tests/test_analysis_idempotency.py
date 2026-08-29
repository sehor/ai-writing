from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.analysis.service import compute_input_hash
from app.cognition.interfaces import (
    CommittedContentEvent,
    ModuleReport,
    ProjectCognitionSnapshot,
    WritingScope,
)
from app.cognition.registry import get_cognition_registry
from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import ManuscriptProposalCreate
from _polling import wait_until


class FailingCognitionRegistry:
    def prepare_context(self, snapshot: ProjectCognitionSnapshot, scope: WritingScope):
        return []

    def ingest_committed_content(
        self, snapshot: ProjectCognitionSnapshot, event: CommittedContentEvent
    ) -> list[ModuleReport]:
        raise RuntimeError("simulated cognition outage")


class AnalysisIdempotencyTests(unittest.TestCase):
    """P1-04: repeated analysis of unchanged input must not duplicate work."""

    def _setup_revision(self, store: SQLiteWritingDataStore, client: TestClient) -> tuple[str, str]:
        project_id = client.post(
            "/api/projects",
            json={
                "title": "Idempotent Novel",
                "premise": "Analysed once, replayed forever.",
            },
        ).json()["id"]
        scene = client.post(
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
        ).json()
        proposal = client.post(
            f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
        ).json()
        accepted = client.put(
            f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
            json={"status": "accepted"},
        )
        assert accepted.status_code == 200
        revision = store.list_manuscript_revisions(project_id)[0]
        return project_id, revision.id

    def _wait_for_automatic_writeback_run(
        self, store: SQLiteWritingDataStore, project_id: str, expected_status: str
    ) -> None:
        """P1-03: the acceptance-time job runs in the background dispatcher."""
        wait_until(
            lambda: [
                job
                for job in store.list_outbox_jobs(
                    project_id, job_status=expected_status
                )
                if job.job_type == "writeback_analysis"
            ],
            timeout_seconds=20,
            message=f"automatic write-back job to reach '{expected_status}'",
        )

    def _post_writebacks(self, client: TestClient, project_id: str, revision_id: str, **params):
        return client.post(
            f"/api/projects/{project_id}/writeback/proposals/from-revision/{revision_id}",
            params=params,
        )

    def test_repeated_request_replays_cached_result_without_duplicates(self) -> None:
        """P1-07: the acceptance-time run is replayed, never duplicated."""
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, revision_id = self._setup_revision(store, client)
                    # The manual requests below replay the automatic run, so
                    # the dispatcher must have finished it first (P1-03).
                    self._wait_for_automatic_writeback_run(store, project_id, "succeeded")

                    first = self._post_writebacks(client, project_id, revision_id)
                    second = self._post_writebacks(client, project_id, revision_id)

                    first_ids = [item["id"] for item in first.json()]
                    second_ids = [item["id"] for item in second.json()]

                    runs = [
                        run
                        for run in store.list_analysis_runs(project_id)
                        if run.processor == "local_writeback"
                    ]
                    stored_proposals = store.list_writeback_proposals(project_id)
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertTrue(first_ids, "local analysis should produce at least one proposal")
        # Both manual requests replay the run the acceptance transaction
        # scheduled automatically, so neither generates anything new.
        self.assertEqual(first.headers.get("X-Analysis-Cached"), "true")
        self.assertEqual(second.headers.get("X-Analysis-Cached"), "true")
        self.assertEqual(
            second.headers.get("X-Analysis-Run-Id"), first.headers.get("X-Analysis-Run-Id")
        )
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "succeeded")
        self.assertEqual(len(stored_proposals), len(first_ids))

    def test_forced_rerun_supersedes_pending_prior_proposals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, revision_id = self._setup_revision(store, client)
                    self._wait_for_automatic_writeback_run(store, project_id, "succeeded")

                    first = self._post_writebacks(client, project_id, revision_id)
                    rerun = self._post_writebacks(client, project_id, revision_id, force=True)

                    runs = [
                        run
                        for run in store.list_analysis_runs(project_id)
                        if run.processor == "local_writeback"
                    ]
                    statuses = {item.status for item in store.list_writeback_proposals(project_id)}
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(rerun.status_code, 201)
        # Same input -> same run row, bumped to a new run version.
        self.assertEqual(
            rerun.headers.get("X-Analysis-Run-Id"),
            first.headers.get("X-Analysis-Run-Id"),
        )
        self.assertEqual(rerun.headers.get("X-Analysis-Run-Version"), "2")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].run_version, 2)
        self.assertIn("superseded", statuses)
        self.assertIn("pending_review", statuses)

    def test_failed_run_is_recorded_and_next_request_regenerates(self) -> None:
        """A cognition outage fails the automatic job without losing core data."""
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            # The outage is active before acceptance, so the P1-07 automatic
            # write-back job already fails; the manual request below must
            # fail the same way until cognition recovers.
            app.dependency_overrides[get_cognition_registry] = lambda: FailingCognitionRegistry()

            try:
                with TestClient(app, raise_server_exceptions=False) as client:
                    project_id, revision_id = self._setup_revision(store, client)

                    # The outage is active before acceptance, so the P1-07
                    # automatic write-back job already fails in the background
                    # dispatcher (P1-03); the manual request below must fail
                    # the same way until cognition recovers.
                    self._wait_for_automatic_writeback_run(store, project_id, "failed")
                    failed_jobs = store.list_outbox_jobs(project_id, job_status="failed")
                    failed = self._post_writebacks(client, project_id, revision_id)

                    app.dependency_overrides.pop(get_cognition_registry, None)
                    recovered = self._post_writebacks(client, project_id, revision_id)

                    runs = [
                        run
                        for run in store.list_analysis_runs(project_id)
                        if run.processor == "local_writeback"
                    ]
                    proposals = store.list_writeback_proposals(project_id)
            finally:
                app.dependency_overrides.clear()

        self.assertTrue(failed_jobs, "acceptance schedules a write-back analysis job")
        self.assertIn("RuntimeError", failed_jobs[0].last_error)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(recovered.status_code, 201)
        self.assertEqual(recovered.headers.get("X-Analysis-Cached"), "false")
        self.assertEqual(len(runs), 1, "failure and recovery share one input key")
        self.assertEqual(runs[0].status, "succeeded")
        self.assertGreaterEqual(runs[0].run_version, 2)
        self.assertTrue(proposals)

    def test_compute_input_hash_is_order_insensitive_and_content_sensitive(
        self,
    ) -> None:
        base = {"a": 1, "list": ["x", "y"]}
        reordered = {"list": ["x", "y"], "a": 1}
        changed = {"a": 1, "list": ["y", "x"]}
        self.assertEqual(compute_input_hash(base), compute_input_hash(reordered))
        self.assertNotEqual(compute_input_hash(base), compute_input_hash(changed))


class ProseExcerptCapTests(unittest.TestCase):
    """P1-03 memory guidance: no full-manuscript copies inside Memory."""

    def test_local_prose_sample_memory_stays_within_the_excerpt_band(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={
                            "title": "Long Chapter",
                            "premise": "A very long scene.",
                        },
                    ).json()["id"]
                    scene = client.post(
                        f"/api/projects/{project_id}/scene-contracts",
                        json={
                            "sequence": 1,
                            "title": "Long Scene",
                            "source_artifact_step": 8,
                        },
                    ).json()
                    long_text = ("Mira counted the shelves. " * 1200).strip()
                    proposal = store.create_manuscript_proposal(
                        project_id,
                        ManuscriptProposalCreate(
                            scene_id=scene["id"],
                            title="1. Long Scene",
                            content=long_text,
                            context="Compiled context.",
                        ),
                    )
                    client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal.id}/status",
                        json={"status": "accepted"},
                    )
                    revision = store.list_manuscript_revisions(project_id)[0]

                    response = client.post(
                        f"/api/projects/{project_id}/writeback/proposals"
                        f"/from-revision/{revision.id}"
                    )

                prose_samples = [
                    item
                    for item in response.json()
                    if item["target"] == "memory_record"
                    and item["payload"].get("record_type") == "prose_sample"
                ]
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(prose_samples), 1)
        content = prose_samples[0]["payload"]["content"]
        self.assertLessEqual(len(content), 6000)
        self.assertIn("characters omitted", content)
        self.assertGreater(len(long_text), 20000)


if __name__ == "__main__":
    unittest.main()
