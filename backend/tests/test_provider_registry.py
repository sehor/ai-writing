"""Remote model gateway registry and route wiring behavior."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.llm import (
    DeepSeekAdapter,
    FakeModelGateway,
    ModelGatewayError,
    ModelGatewayRegistry,
    default_model_gateway_registry,
    resolve_default_model_gateway,
)
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.local_backend import LocalFileLlmWiki
from app.main import app


class ModelGatewayRegistryTests(unittest.TestCase):
    def test_default_registry_registers_remote_gateways_only(self) -> None:
        self.assertEqual(default_model_gateway_registry.names(), ["deepseek", "openrouter"])

    def test_unknown_gateway_is_reported_not_configured(self) -> None:
        registry = ModelGatewayRegistry()
        with self.assertRaises(ModelGatewayError) as raised:
            registry.create("missing")
        self.assertEqual(raised.exception.code, "not_configured")

    def test_unconfigured_deepseek_raises_not_configured(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_BASE_URL": "",
            "DEEPSEEK_BASE_URL_FOR_OPENAI": "",
            "DEEPSEEK_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(ModelGatewayError) as raised:
                default_model_gateway_registry.create("deepseek")
        self.assertEqual(raised.exception.code, "not_configured")

    def test_unconfigured_openrouter_needs_no_real_key_for_catalog_or_fake_tests(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
            with self.assertRaises(ModelGatewayError) as raised:
                default_model_gateway_registry.create(
                    "openrouter", "google/gemini-3.8-flash"
                )
        self.assertEqual(raised.exception.code, "not_configured")

    def test_openrouter_registry_applies_allowlisted_model_override_without_calling_network(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=False):
            gateway = default_model_gateway_registry.create(
                "openrouter", "anthropic/claude-fable-5.1"
            )
        self.assertEqual(gateway.describe().provider_id, "openrouter")
        self.assertEqual(gateway.describe().model_id, "anthropic/claude-fable-5.1")

    def test_invalid_deepseek_env_raises_configuration_error(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_TEMPERATURE": "not-a-number",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(ModelGatewayError) as raised:
                default_model_gateway_registry.create("deepseek")
        self.assertEqual(raised.exception.code, "configuration")
        self.assertNotIn("not-a-number", raised.exception.safe_message)

    def test_valid_deepseek_env_resolves_gateway_with_status_info(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_MODEL": "test-model",
            "DEEPSEEK_TEMPERATURE": "0.5",
            "DEEPSEEK_MAX_TOKENS": "128",
        }
        with patch.dict(os.environ, env, clear=False):
            gateway = default_model_gateway_registry.create("deepseek")
        self.assertIsInstance(gateway, DeepSeekAdapter)
        self.assertEqual(gateway.describe().model_id, "test-model")

    def test_custom_gateway_can_be_registered_and_resolved(self) -> None:
        gateway = FakeModelGateway()
        registry = ModelGatewayRegistry()
        registry.register("echo", lambda: gateway)
        resolved, skip_reason = resolve_default_model_gateway(registry, priority=("echo",))
        self.assertIs(resolved, gateway)
        self.assertIsNone(skip_reason)


class RegistryRouteWiringTests(unittest.TestCase):
    def test_snowflake_generation_falls_back_to_local_runtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            wiki = LocalFileLlmWiki(Path(temp_dir) / "wiki")
            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_llm_wiki] = lambda: wiki
            env = {"DEEPSEEK_API_KEY": "", "DEEPSEEK_TEMPERATURE": "0.7"}
            try:
                with patch.dict(os.environ, env, clear=False):
                    with TestClient(app) as client:
                        project_id = client.post(
                            "/api/projects",
                            json={
                                "title": "Registry Wiring",
                                "premise": "Gateways resolve behind one interface.",
                            },
                        ).json()["id"]

                        status_response = client.get("/api/snowflake/workflow/status")
                        self.assertEqual(status_response.status_code, 200)
                        payload = status_response.json()
                        self.assertEqual(payload["provider"], "local")
                        self.assertEqual(payload["runtime_kind"], "local_deterministic")
                        self.assertFalse(payload["provider_configured"])

                        generated = client.post(
                            "/api/snowflake/generate",
                            json={
                                "project_id": project_id,
                                "step_number": 1,
                                "user_input": "One sentence promise.",
                            },
                        )
                        self.assertEqual(generated.status_code, 200)
                        self.assertEqual(generated.headers.get("deprecation"), "true")
                        self.assertIn("/snowflake/generations", generated.headers.get("link", ""))
                        self.assertTrue(generated.json()["content"])
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
