import inspect
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cognition.registry import get_cognition_registry
from app.data import get_data_store
from app.dependencies import get_compile_service, get_manuscript_service
from app.errors import (
    InvalidOperationError,
    ProviderConfigurationError,
    ProviderExecutionError,
    ResourceNotFoundError,
    StateConflictError,
)
from app.http_errors import install_application_error_handlers
from app.llm import ModelGatewayError
from app.models import ManuscriptProposalAcceptance, ManuscriptSceneUpdate
from app.outbox.dispatcher import get_outbox_dispatcher
from app.routers import manuscript, scenes
from app.services.compile_service import CompileService
from app.services.manuscript_service import ManuscriptService


class ApplicationServiceBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Synthetic ports: no default database, background loop or paid model calls.
        self.store = Mock()
        self.store.project_exists.return_value = True
        self.service = ManuscriptService(self.store, None)
        self.app = FastAPI()
        install_application_error_handlers(self.app)
        self.app.include_router(manuscript.router, prefix="/api")
        self.app.include_router(scenes.router, prefix="/api")
        self.app.dependency_overrides[get_data_store] = lambda: self.store
        self.app.dependency_overrides[get_cognition_registry] = lambda: None
        self.app.dependency_overrides[get_manuscript_service] = lambda: self.service
        self.app.dependency_overrides[get_outbox_dispatcher] = lambda: Mock()
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.update = ManuscriptSceneUpdate(
            title="Author title", content="Author text", expected_scene_version=1
        )

    def test_core_imports_do_not_load_http_or_execution_wiring(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; "
                "import app.services.manuscript_service, app.services.compile_service, "
                "app.services.reference_service, app.services.writeback_service, "
                "app.services.snowflake_service, app.services.model_service, app.review.service; "
                "assert not set(sys.modules).intersection("
                "['fastapi', 'app.dependencies', 'app.analysis.http', 'app.outbox.handlers'])",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_service_dependencies_are_explicit_and_factories_share_the_supplied_ports(self):
        for cls in (ManuscriptService, CompileService):
            signature = inspect.signature(cls)
            for parameter in ("data_store", "cognition"):
                self.assertIs(signature.parameters[parameter].default, inspect.Parameter.empty)
        for factory in (get_manuscript_service, get_compile_service):
            instance = factory(self.store, None)
            self.assertIs(instance.data_store, self.store)
            self.assertIsNone(instance.cognition)

    def test_not_found_is_an_application_error_and_preserves_http_detail(self):
        self.store.update_manuscript_scene.return_value = None
        with self.assertRaises(ResourceNotFoundError) as raised:
            self.service.update_scene("p", "missing", self.update)
        response = self.client.put(
            "/api/projects/p/manuscript/scenes/missing", json=self.update.model_dump()
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": raised.exception.detail})

    def test_compile_factory_uses_overridden_data_and_maps_missing_scene(self):
        self.store.get_scene_contract.return_value = None
        with self.assertRaises(ResourceNotFoundError):
            CompileService(self.store, None).compile_scene_contract("p", "missing")
        response = self.client.post("/api/projects/p/scene-contracts/missing/compile")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Scene contract not found."})

    def test_stale_write_is_an_application_conflict_and_http_409(self):
        self.store.update_manuscript_scene.side_effect = ValueError(
            "Expected version 1, current 2."
        )
        with self.assertRaises(StateConflictError) as raised:
            self.service.update_scene("p", "s", self.update)
        response = self.client.put(
            "/api/projects/p/manuscript/scenes/s", json=self.update.model_dump()
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": raised.exception.detail})

    def test_consistency_gate_preserves_structured_details_and_legacy_error_headers(self):
        self.store.get_manuscript_proposal.return_value = SimpleNamespace(
            status="pending_review", title="Title", content="Text", scene_id="s"
        )
        self.store.get_manuscript_scene.return_value = None
        evidence = {"summary": {"critical_count": 1}, "findings": [{"rule": "canon"}]}
        report = SimpleNamespace(
            summary=SimpleNamespace(critical_count=1), model_dump=lambda: evidence
        )
        draft = ManuscriptProposalAcceptance(
            title="Title", content="Text", expected_scene_version=0
        )
        with patch.object(self.service, "preview_proposal_consistency", return_value=report):
            with self.assertRaises(InvalidOperationError) as raised:
                self.service.update_proposal_status("p", "proposal", "accepted", draft)
            response = self.client.post(
                "/api/projects/p/manuscript/proposals/proposal/accept", json=draft.model_dump()
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json(), {"detail": raised.exception.detail})
            legacy = self.client.put(
                "/api/projects/p/manuscript/proposals/proposal/status", json={"status": "accepted"}
            )
        self.assertEqual(legacy.status_code, 422)
        self.assertEqual(legacy.json(), response.json())
        self.assertEqual(legacy.headers["Deprecation"], "true")
        self.assertIn('rel="successor-version"', legacy.headers["Link"])
        self.store.accept_manuscript_proposal.assert_not_called()

    def test_provider_errors_preserve_safe_details_and_configuration_distinction(self):
        for code, error_type, http_status in (
            ("not_configured", ProviderConfigurationError, 501),
            ("timeout", ProviderExecutionError, 502),
        ):
            with self.subTest(code=code):
                failure = ModelGatewayError(code, "Safe provider failure")
                with (
                    patch.object(self.service, "_build_snapshot", return_value=Mock()),
                    patch(
                        "app.services.manuscript_service.generate_manuscript_scene",
                        side_effect=failure,
                    ),
                ):
                    with self.assertRaises(error_type) as raised:
                        self.service.generate_provider_proposal("p", "s")
                    response = self.client.post(
                        "/api/projects/p/manuscript/proposals/from-scene/s/provider"
                    )
                self.assertIs(raised.exception.__cause__, failure)
                self.assertEqual(response.status_code, http_status)
                self.assertEqual(response.json(), {"detail": "Safe provider failure"})

    def test_event_contract_import_does_not_load_handlers_or_data(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import app.outbox.events; "
                "assert not set(sys.modules).intersection("
                "['app.outbox.handlers', 'app.data', 'app.llm_wiki.interfaces', 'fastapi'])",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_compatibility_exports_are_the_same_event_factories_and_dependency(self):
        from app.analysis.http import get_analysis_service as compatibility_factory
        from app.dependencies import get_analysis_service
        from app.outbox import events, handlers

        self.assertIs(compatibility_factory, get_analysis_service)
        for name in (
            "snowflake_index_payload",
            "manuscript_revision_index_payload",
            "manuscript_revision_analysis_payload",
        ):
            self.assertIs(getattr(handlers, name), getattr(events, name))


if __name__ == "__main__":
    unittest.main()
