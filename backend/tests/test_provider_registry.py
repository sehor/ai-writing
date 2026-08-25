"""P2-02 provider registry behavior.

Resolution order, configuration errors, and fallback semantics are
covered here; route-level provider failures stay covered by the
review-loop route tests.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.integrations.provider_registry import (
    DeepSeekProvider,
    LocalDeterministicProvider,
    ProviderConfigurationError,
    ProviderDependencies,
    ProviderNotConfiguredError,
    ProviderRegistry,
    default_provider_registry,
    resolve_default_provider,
)
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.local_backend import LocalFileLlmWiki
from app.main import app


def _deps() -> ProviderDependencies:
    return ProviderDependencies()


class EchoProvider:
    name = "echo"

    def generate_snowflake(self, request, *, data_store, steps, llm_wiki):
        raise NotImplementedError

    def generate_manuscript(self, scene, context):
        raise NotImplementedError

    def generate_reference(self, request, *, context, snapshot, cognition_context):
        raise NotImplementedError

    def generate_writebacks(self, revision, snapshot):
        raise NotImplementedError


class ProviderRegistryTests(unittest.TestCase):
    def test_default_registry_registers_local_and_deepseek(self) -> None:
        self.assertEqual(default_provider_registry.names(), ["deepseek", "local"])

    def test_local_provider_is_always_available(self) -> None:
        provider = default_provider_registry.create("local", _deps())
        self.assertIsInstance(provider, LocalDeterministicProvider)
        self.assertIsNone(default_provider_registry.configuration_problem("local", _deps()))

    def test_unknown_provider_is_reported_not_configured(self) -> None:
        registry = ProviderRegistry()
        with self.assertRaises(ProviderNotConfiguredError):
            registry.create("missing", _deps())

    def test_unconfigured_deepseek_raises_not_configured(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_BASE_URL": "",
            "DEEPSEEK_BASE_URL_FOR_OPENAI": "",
            "DEEPSEEK_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(ProviderNotConfiguredError):
                default_provider_registry.create("deepseek", _deps())
            problem = default_provider_registry.configuration_problem("deepseek", _deps())
        self.assertIsNotNone(problem)

    def test_invalid_deepseek_env_raises_configuration_error(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_TEMPERATURE": "not-a-number",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(ProviderConfigurationError):
                default_provider_registry.create("deepseek", _deps())
            problem = default_provider_registry.configuration_problem("deepseek", _deps())
        self.assertIn("not-a-number", problem or "")

    def test_valid_deepseek_env_resolves_provider_with_status_info(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_MODEL": "test-model",
            "DEEPSEEK_TEMPERATURE": "0.5",
            "DEEPSEEK_MAX_TOKENS": "128",
        }
        with patch.dict(os.environ, env, clear=False):
            provider = default_provider_registry.create("deepseek", _deps())
        self.assertIsInstance(provider, DeepSeekProvider)
        described = provider.describe()
        self.assertEqual(described["model"], "test-model")

    def test_resolution_prefers_configured_priority_order(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_TEMPERATURE": "0.7",
        }
        with patch.dict(os.environ, env, clear=False):
            provider, skip_reason = resolve_default_provider(_deps())
        self.assertIsInstance(provider, DeepSeekProvider)
        self.assertIsNone(skip_reason)

    def test_resolution_falls_back_to_local_when_provider_unconfigured(self) -> None:
        env = {
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_TEMPERATURE": "0.7",
        }
        with patch.dict(os.environ, env, clear=False):
            provider, skip_reason = resolve_default_provider(_deps())
        self.assertIsInstance(provider, LocalDeterministicProvider)
        self.assertIsNotNone(skip_reason)
        self.assertIn("deepseek", skip_reason or "")

    def test_custom_provider_can_be_registered_and_resolved_first(self) -> None:
        registry = ProviderRegistry()
        registry.register("echo", lambda deps: EchoProvider())
        registry.register("local", lambda deps: LocalDeterministicProvider())
        provider, skip_reason = resolve_default_provider(
            _deps(), registry=registry, priority=("echo", "local")
        )
        self.assertIsInstance(provider, EchoProvider)
        self.assertIsNone(skip_reason)

        # A factory returning None means "known but not usable".
        empty = ProviderRegistry()
        empty.register("echo", lambda deps: None)
        empty.register("local", lambda deps: LocalDeterministicProvider())
        fallback, fallback_reason = resolve_default_provider(
            _deps(), registry=empty, priority=("echo", "local")
        )
        self.assertIsInstance(fallback, LocalDeterministicProvider)
        self.assertIsNotNone(fallback_reason)


class RegistryRouteWiringTests(unittest.TestCase):
    def test_snowflake_generation_uses_registry_backed_default(self) -> None:
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
                                "premise": "Providers resolve behind one interface.",
                            },
                        ).json()["id"]

                        status_response = client.get("/api/snowflake/workflow/status")
                        self.assertEqual(status_response.status_code, 200)
                        payload = status_response.json()
                        self.assertEqual(payload["provider"], "local")
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
                        self.assertTrue(generated.json()["content"])
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
