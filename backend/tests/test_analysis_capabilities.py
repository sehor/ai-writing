"""AUD-20: execution evidence must distinguish skipped work from a clean report."""

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import httpx
from test_clp_sidecar import _request, _valid_result
from app.integrations.llmwiki_clp import LlmWikiClpClient, KnowledgeCompilerResponseError
from app.services.backup_service import ProjectBackupService

from test_clp_sidecar import NoopWiki, _accepted_revision_store
from app.data import SQLiteWritingDataStore
from app.outbox.service import OutboxService
from app.integrations.llmwiki_clp import UnavailableKnowledgeCompiler


class AnalysisCapabilityTests(unittest.TestCase):
    def test_clp_rejects_evidence_not_present_in_the_named_revision(self):
        payload = _valid_result().model_dump(mode="json")
        payload["entity_candidates"][0]["evidence"][0]["excerpt"] = "Invented source quotation"
        with httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ) as http:
            compiler = LlmWikiClpClient(compiler_version="llmwiki-clp-test", http_client=http)
            with self.assertRaises(KnowledgeCompilerResponseError):
                compiler.extract_revision(_request())

    def test_execution_evidence_round_trips_through_backup(self):
        with TemporaryDirectory() as root:
            store, project, _, _, _ = _accepted_revision_store(root)
            job = next(j for j in store.list_outbox_jobs(project) if j.job_type == "clp_extraction")
            result = OutboxService(store, NoopWiki()).process_job(project, job.id)
            service = ProjectBackupService(store, Path(root) / "projects")
            package = service.export_package(project)
            other = SQLiteWritingDataStore(Path(root) / "other.db")
            other.init()
            ProjectBackupService(other, Path(root) / "restored").import_package(package)
            self.assertEqual(other.get_outbox_job(project, job.id).execution, result.execution)

    def test_disabled_clp_is_persisted_as_not_executed_not_semantic_success(self):
        with TemporaryDirectory() as root:
            store, project, _, _, _ = _accepted_revision_store(root)
            job = next(j for j in store.list_outbox_jobs(project) if j.job_type == "clp_extraction")
            result = OutboxService(store, NoopWiki()).process_job(project, job.id)
            self.assertEqual(result.execution.mode, "not_configured")
            self.assertEqual(result.execution.outcome, "not_executed")
            self.assertFalse(result.execution.semantic_review)
            reopened = SQLiteWritingDataStore(store.database_path)
            self.assertEqual(reopened.get_outbox_job(project, job.id).execution, result.execution)
            self.assertEqual(store.list_writeback_proposals(project), [])

    def test_local_rule_success_does_not_claim_semantic_review(self):
        with TemporaryDirectory() as root:
            store, project, _, _, _ = _accepted_revision_store(root)
            job = next(
                j for j in store.list_outbox_jobs(project) if j.job_type == "consistency_analysis"
            )
            result = OutboxService(store, NoopWiki()).process_job(project, job.id)
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.execution.mode, "local_rules")
            self.assertEqual(result.execution.outcome, "limited")
            self.assertIn("语义", result.execution.limitations)
            self.assertTrue(result.execution.source_ref)

    def test_configuration_failure_is_visible_and_keeps_authoritative_revision(self):
        with TemporaryDirectory() as root:
            store, project, _, _, revision = _accepted_revision_store(root)
            compiler = UnavailableKnowledgeCompiler(
                compiler_version="test", error=ValueError("invalid configuration")
            )
            service = OutboxService(store, NoopWiki(), compiler=compiler)
            job = next(j for j in store.list_outbox_jobs(project) if j.job_type == "clp_extraction")
            result = service.process_job(project, job.id)
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.execution.outcome, "failed")
            self.assertEqual(result.execution.mode, "unavailable")
            self.assertEqual(store.get_manuscript_revision(project, revision.id), revision)
            self.assertEqual(store.list_writeback_proposals(project), [])
            queued = service.retry(project, job.id)
            self.assertIsNone(queued.execution)
