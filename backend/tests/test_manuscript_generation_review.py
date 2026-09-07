import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.data import migrations
from app.data.unit_of_work import open_connection
from app.llm import FakeModelGateway, ModelGatewayRegistry
from app.models import ManuscriptProposalCreate, ProjectCreate, SceneContractCreate
from app.routers.manuscript import router
from app.services.backup_service import ProjectBackupService
from app.services.manuscript_service import ManuscriptService


class ManuscriptGenerationReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SQLiteWritingDataStore(self.root / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Review", premise="A city moves.")
        )
        self.scene = self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=1, title="The gate")
        )
        self.material = {
            "scene_id": self.scene.id,
            "manuscript_prose": "She unlocks the gate.",
            "entry_state_observed": ["Gate locked"],
            "exit_state_produced": ["Gate open"],
            "scene_contract_coverage": {
                "goal": "Reached",
                "conflict": "Lock",
                "turning_point": "Key fits",
                "outcome": "Gate opens",
                "missing_elements": ["Cost"],
            },
            "new_fact_candidates": [
                {
                    "claim": "The key is brass",
                    "entity_refs": ["key"],
                    "reason_introduced": "Explains the mechanism",
                    "status": "proposal",
                }
            ],
            "design_deviation_proposals": [
                {
                    "target_artifact_ref": "step:8",
                    "current_design": "Gate stays closed",
                    "proposed_change": "Open the gate",
                    "reason": "Maintains momentum",
                    "downstream_impact": ["Revise next scene"],
                }
            ],
            "continuity_questions": ["Who owns the key?"],
            "source_refs": ["scene:gate"],
        }

    def generate(self, content):
        gateway = FakeModelGateway([content])
        registry = ModelGatewayRegistry()
        registry.register("deepseek", lambda: gateway)
        service = ManuscriptService(data_store=self.store, cognition=None)
        service.gateway_registry = registry
        return service.generate_provider_proposal(self.project.id, self.scene.id)

    def assert_material(self, proposal):
        review = proposal.generation_review
        self.assertEqual(review.schema_version, 1)
        self.assertEqual(review.availability, "structured")
        self.assertEqual(review.provider, "fake")
        self.assertTrue(review.generation_run_id)
        for key, value in self.material.items():
            self.assertEqual(review.material.model_dump()[key], value, key)

    def test_generation_restart_api_and_backup_preserve_every_field(self):
        proposal = self.generate(json.dumps(self.material))
        self.assert_material(proposal)
        reopened = SQLiteWritingDataStore(self.root / "app.db")
        reopened.init()
        self.assert_material(reopened.get_manuscript_proposal(self.project.id, proposal.id))
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_data_store] = lambda: reopened
        with TestClient(app) as client:
            response = client.get(f"/api/projects/{self.project.id}/manuscript/proposals")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()[0]["generation_review"], proposal.generation_review.model_dump()
            )
        backup = ProjectBackupService(reopened, self.root / "projects")
        package = backup.export_package(self.project.id)
        with ZipFile(io.BytesIO(package)) as archive:
            self.assertIn(
                "generation_review_json",
                str([archive.read(name) for name in archive.namelist() if name.endswith(".json")]),
            )
        target = SQLiteWritingDataStore(self.root / "restored.db")
        target.init()
        ProjectBackupService(target, self.root / "restored-projects").import_package(package)
        self.assert_material(target.get_manuscript_proposal(self.project.id, proposal.id))
        self.assertEqual(target.list_manuscript_scenes(self.project.id), [])

    def test_legacy_prose_has_explicit_missing_material_and_old_proposals_stay_readable(self):
        proposal = self.generate("Legacy prose only.")
        self.assertEqual(proposal.generation_review.availability, "legacy_prose_only")
        self.assertIsNone(proposal.generation_review.material)
        old = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(
                scene_id=self.scene.id,
                title="Old proposal",
                content="Old prose",
            ),
        )
        self.assertIsNone(
            self.store.get_manuscript_proposal(self.project.id, old.id).generation_review
        )

    def test_review_column_migration_rolls_back_and_can_retry(self):
        connection = open_connection(self.root / "legacy.db")
        try:
            with patch.object(
                migrations, "MIGRATIONS", [m for m in migrations.MIGRATIONS if m.version < 13]
            ):
                migrations.run_migrations(connection)
            original = migrations.ensure_column

            def fail_after_column(*args):
                original(*args)
                raise RuntimeError("injected failure")

            with patch.object(migrations, "ensure_column", fail_after_column):
                with self.assertRaises(RuntimeError):
                    migrations.run_migrations(connection)
            self.assertNotIn(
                "generation_review_json",
                {row[1] for row in connection.execute("PRAGMA table_info(manuscript_proposals)")},
            )
            self.assertNotIn(13, migrations.applied_versions(connection))
            migrations.run_migrations(connection)
            self.assertIn(
                "generation_review_json",
                {row[1] for row in connection.execute("PRAGMA table_info(manuscript_proposals)")},
            )
        finally:
            connection.close()
