"""P1-07: accepting a manuscript proposal schedules its analyses automatically.

The acceptance transaction enqueues one Wiki-index job plus consistency and
write-back analysis jobs per created revision. Dispatch happens right after
commit: reports appear without a manual trigger, generated write-backs stay
pending_review (analysis is automatic, accepting them is not), and a failing
analysis never endangers the accepted core data.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

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


class RecordingLlmWiki:
    """Minimal LlmWiki stub that records ingested documents."""

    def __init__(self) -> None:
        self.documents: list[WikiSourceDocument] = []

    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        self.documents.append(document)
        return WikiIngestionResult(status="stored", source_ref=document.source_ref)

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        return WikiContextResult(summary="stub", evidence=[], constraints=[])

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        return WikiInsightResult(summary="stub", insights=[])


class PostAcceptAnalysisTests(unittest.TestCase):
    def _install(self, temp_dir: str, wiki: RecordingLlmWiki) -> SQLiteWritingDataStore:
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        app.dependency_overrides[get_data_store] = lambda: store
        app.dependency_overrides[get_llm_wiki] = lambda: wiki
        app.dependency_overrides[get_writing_workflow] = lambda: LocalDraftWritingWorkflow(
            store, SNOWFLAKE_STEPS, wiki
        )
        return store

    def _accept_one_revision(self, client: TestClient):
        project_id = client.post(
            "/api/projects",
            json={"title": "Auto Analysis Novel", "premise": "Reports without asking."},
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
                "required_canon": "Mira",
                "forbidden_facts": "the archive burned down",
                "source_artifact_step": 8,
            },
        ).json()
        scene_id = scene["id"]
        proposal = client.post(
            f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene_id}"
        ).json()
        proposal_id = proposal["id"]
        accepted = client.put(
            f"/api/projects/{project_id}/manuscript/proposals/{proposal_id}/status",
            json={"status": "accepted"},
        )
        self.assertEqual(accepted.status_code, 200)
        return project_id, accepted

    def test_acceptance_enqueues_and_runs_both_analysis_jobs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = RecordingLlmWiki()
            store = self._install(temp_dir, wiki)
            try:
                with TestClient(app) as client:
                    project_id, accepted = self._accept_one_revision(client)

                    revisions = store.list_manuscript_revisions(project_id)
                    jobs = store.list_outbox_jobs(project_id)
                    report_response = client.get(
                        f"/api/projects/{project_id}/analysis/consistency"
                        f"/from-revision/{revisions[0].id}",
                    )
                    proposals = store.list_writeback_proposals(project_id)
                    runs = store.list_analysis_runs(project_id)
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(len(revisions), 1)

        # Both post-commit job groups report success on the response itself.
        self.assertEqual(accepted.headers.get("X-Wiki-Index-Status"), "succeeded")
        self.assertEqual(accepted.headers.get("X-Analysis-Job-Status"), "succeeded")

        # Three jobs left the acceptance transaction: index + two analyses.
        self.assertEqual(
            sorted(job.job_type for job in jobs),
            ["consistency_analysis", "llm_wiki_ingest", "writeback_analysis"],
        )
        self.assertTrue(all(job.status == "succeeded" for job in jobs))
        for job in jobs:
            self.assertEqual(job.aggregate_id, revisions[0].id)

        # The consistency report is retrievable without any manual run.
        self.assertEqual(report_response.status_code, 200)
        report = report_response.json()
        self.assertTrue(report["cached"], "GET replays the automatic run")
        self.assertEqual(report["run_version"], 1)

        # Write-back analysis produced reviewable proposals - pending only.
        self.assertTrue(proposals)
        self.assertTrue(
            all(item.status == "pending_review" for item in proposals),
            "automatic analysis must not auto-accept write-backs",
        )

        # One succeeded run row per processor came out of the same dispatch.
        self.assertEqual(
            sorted(run.processor for run in runs),
            ["consistency_checker", "local_writeback"],
        )
        self.assertTrue(all(run.status == "succeeded" for run in runs))

    def test_failing_consistency_check_is_isolated_and_retryable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = RecordingLlmWiki()
            store = self._install(temp_dir, wiki)
            try:
                with TestClient(app) as client:
                    with mock.patch(
                        "app.analysis.consistency.check_revision",
                        side_effect=RuntimeError("simulated checker outage"),
                    ):
                        project_id, accepted = self._accept_one_revision(client)

                    revisions = store.list_manuscript_revisions(project_id)
                    failed_jobs = store.list_outbox_jobs(project_id, job_status="failed")
                    retried = client.post(
                        f"/api/projects/{project_id}/outbox-jobs/{failed_jobs[0].id}/retry"
                    )
                    report_response = client.get(
                        f"/api/projects/{project_id}/analysis/consistency"
                        f"/from-revision/{revisions[0].id}",
                    )
                    outbox = OutboxService(data_store=store, wiki=wiki)
                    processed_again = outbox.process_pending(project_id)
                    succeeded_jobs = [
                        job.job_type
                        for job in store.list_outbox_jobs(project_id)
                        if job.status == "succeeded"
                    ]
                    proposals_after = store.list_writeback_proposals(project_id)
                    revisions_after = store.list_manuscript_revisions(project_id)
            finally:
                app.dependency_overrides.clear()

        # Core data survived the checker outage and the response says where
        # the automatic analysis stopped.
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.headers.get("X-Analysis-Job-Status"), "failed")
        self.assertIn("X-Analysis-Job-Id", accepted.headers)
        self.assertIn("Core data saved", accepted.headers["X-Analysis-Job-Message"])
        self.assertEqual(len(revisions), 1)

        # Exactly the consistency job failed; wiki and write-back succeeded.
        self.assertEqual(len(failed_jobs), 1)
        self.assertEqual(failed_jobs[0].job_type, "consistency_analysis")
        self.assertIn("RuntimeError", failed_jobs[0].last_error)
        self.assertEqual(
            sorted(succeeded_jobs),
            ["consistency_analysis", "llm_wiki_ingest", "writeback_analysis"],
        )

        # Recovery: retry marks the job succeeded and the report appears.
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["status"], "succeeded")
        self.assertEqual(report_response.status_code, 200)

        # Re-dispatching finds nothing pending and duplicates nothing.
        self.assertEqual(processed_again, [])
        self.assertEqual(len(revisions_after), 1)
        self.assertGreaterEqual(len(proposals_after), 1)


if __name__ == "__main__":
    unittest.main()
