import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.reference_workflow import generate_gateway_reference_suggestion
from app.cognition.registry import CognitionRegistry
from app.data import SQLiteWritingDataStore, get_data_store
from app.dependencies import get_reference_service
from app.http_errors import install_application_error_handlers
from app.llm import FakeModelGateway
from app.models import (
    ManuscriptProposalCreate,
    ManuscriptSceneUpdate,
    ProjectCreate,
    ReferenceGenerationRequest,
    SceneContractCreate,
)
from app.routers.references import router
from app.services.backup_service import ProjectBackupService
from app.services.reference_service import ReferenceService


class ReferenceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SQLiteWritingDataStore(self.root / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Selection", premise="A letter changes hands.")
        )
        self.scene = self.store.create_scene_contract(
            self.project.id,
            SceneContractCreate(sequence=1, title="Letter", pov="Mira", goal="Find the author"),
        )
        self.proposal = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(
                scene_id=self.scene.id, title="Letter", content="Saved original."
            ),
        )
        self.service = ReferenceService(self.store, CognitionRegistry(self.root / "modules"))
        app = FastAPI()
        install_application_error_handlers(app)
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_data_store] = lambda: self.store
        app.dependency_overrides[get_reference_service] = lambda: self.service
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = f"/api/projects/{self.project.id}/references/suggestions/generate"

    def payload(self, **changes):
        editor = {
            "project_id": self.project.id,
            "scene_id": self.scene.id,
            "source_kind": "proposal_draft",
            "proposal_id": self.proposal.id,
            "expected_scene_version": 0,
            "session_id": "session-1",
            "snapshot_text": "前文😀选中秘密。后文",
            "selection_mode": "selection",
            "selection_start": 4,
            "selection_end": 8,
            "selected_text": "选中秘密",
        }
        editor.update(changes)
        return {
            "suggestion_type": "prose_reference",
            "scope_type": "scene",
            "scope_ref": self.scene.id,
            "author_problem": "让这句话更含蓄",
            "editor_context": editor,
        }

    def test_unsaved_selection_survives_api_reload_without_modifying_source(self):
        payload = self.payload()
        response = self.client.post(self.url, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        suggestion = response.json()
        self.assertEqual(suggestion["editor_context"], payload["editor_context"])
        for text in ("选中秘密", "让这句话更含蓄", "Find the author", "session-1"):
            self.assertIn(text, suggestion["used_context"])
        reopened = SQLiteWritingDataStore(self.root / "app.db")
        self.assertEqual(
            reopened.list_reference_suggestions(self.project.id)[0].model_dump(mode="json"),
            suggestion,
        )
        self.assertEqual(
            reopened.get_manuscript_proposal(self.project.id, self.proposal.id), self.proposal
        )
        self.assertEqual(reopened.list_manuscript_revisions(self.project.id), [])
        self.assertEqual(reopened.list_canon_entities(self.project.id), [])

    def test_fake_gateway_receives_selection_and_intent_in_actual_prompt(self):
        request = ReferenceGenerationRequest.model_validate(self.payload())
        snapshot, cognition, context = self.service._assemble(self.project.id, request)
        fake = FakeModelGateway(["一封迟到的信，让她停住了脚步。"])
        generated = generate_gateway_reference_suggestion(
            fake, request, context, snapshot, cognition
        )
        prompt = "\n".join(message.content for message in fake.requests[0].prompt.messages)
        for text in ("选中秘密", "让这句话更含蓄", "Find the author", self.scene.id):
            self.assertIn(text, prompt)
        self.assertEqual(generated.suggestion.editor_context, request.editor_context)

    def test_whole_scene_and_accepted_manuscript_sources(self):
        accepted = self.store.accept_manuscript_proposal(self.project.id, self.proposal.id)
        payload = self.payload(
            source_kind="accepted_manuscript",
            proposal_id="",
            expected_scene_version=accepted.version,
            snapshot_text="整场景😀",
            selected_text="整场景😀",
            selection_mode="whole_scene",
            selection_start=0,
            selection_end=5,
        )
        response = self.client.post(self.url, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["editor_context"]["selection_mode"], "whole_scene")
        self.assertEqual(self.store.get_manuscript_scene(self.project.id, self.scene.id), accepted)

    def test_invalid_offsets_unicode_blank_and_snapshot_mismatch_are_422(self):
        for changes in (
            {"selection_start": 3},
            {"selection_end": 999},
            {"selected_text": "Other"},
            {"selection_start": True},
            {"selection_mode": "whole_scene"},
            {"snapshot_text": " ", "selected_text": " ", "selection_start": 0, "selection_end": 1},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.client.post(self.url, json=self.payload(**changes)).status_code, 422
                )
        self.assertEqual(self.store.list_reference_suggestions(self.project.id), [])

    def test_foreign_targets_and_stale_versions_cannot_generate(self):
        other = self.store.create_project(ProjectCreate(title="Other", premise="Private."))
        for changes, status in (
            ({"project_id": other.id}, 404),
            ({"scene_id": "missing"}, 422),
            ({"proposal_id": "missing"}, 404),
            ({"expected_scene_version": 3}, 409),
        ):
            response = self.client.post(self.url, json=self.payload(**changes))
            self.assertEqual(response.status_code, status, response.text)
        self.store.update_manuscript_proposal_status(self.project.id, self.proposal.id, "rejected")
        self.assertEqual(self.client.post(self.url, json=self.payload()).status_code, 409)

    def test_version_changed_during_provider_work_is_not_persisted(self):
        accepted = self.store.accept_manuscript_proposal(self.project.id, self.proposal.id)
        payload = self.payload(
            source_kind="accepted_manuscript",
            proposal_id="",
            expected_scene_version=accepted.version,
        )

        def generate(*args, **kwargs):
            self.store.update_manuscript_scene(
                self.project.id,
                self.scene.id,
                ManuscriptSceneUpdate(
                    title="New", content="Changed concurrently", expected_scene_version=1
                ),
            )
            return SimpleNamespace(suggestion=None)

        with patch(
            "app.services.reference_service.generate_gateway_reference_suggestion",
            side_effect=generate,
        ):
            response = self.client.post(self.url + "/provider", json=payload)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.store.list_reference_suggestions(self.project.id), [])

    def test_new_and_old_backup_restore_selection_provenance(self):
        response = self.client.post(self.url, json=self.payload())
        self.assertEqual(response.status_code, 201, response.text)
        package = ProjectBackupService(self.store, self.root / "projects").export_package(
            self.project.id
        )
        target = SQLiteWritingDataStore(self.root / "restored.db")
        target.init()
        restore = ProjectBackupService(target, self.root / "restored-projects")
        restore.import_package(package)
        self.assertEqual(
            target.list_reference_suggestions(self.project.id),
            self.store.list_reference_suggestions(self.project.id),
        )
        with ZipFile(io.BytesIO(package)) as source:
            files = {name: source.read(name) for name in source.namelist()}
        manifest = json.loads(files["manifest.json"])
        manifest["schema_version"] = 16
        tables = json.loads(files["data.json"])
        for table in ("manuscript_volumes", "manuscript_volume_chapters"):
            tables["tables"].pop(table)
            manifest["tables"].remove(table)
            manifest["project"]["row_counts"].pop(table)
        for row in tables["tables"]["outbox_jobs"]:
            row.pop("execution_json", None)
        for row in tables["tables"]["reference_suggestions"]:
            row.pop("editor_context_json")
        files["manifest.json"] = json.dumps(manifest).encode()
        files["data.json"] = json.dumps(tables).encode()
        older = io.BytesIO()
        with ZipFile(older, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        restore.import_package(older.getvalue(), overwrite=True)
        self.assertIsNone(target.list_reference_suggestions(self.project.id)[0].editor_context)
