from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from app.data import SQLiteWritingDataStore
from app.llm import (
    FakeGatewayScenario,
    FakeModelGateway,
    ModelCapabilities,
    ModelCatalog,
    ModelGatewayError,
    ModelGatewayRegistry,
    ModelProfile,
    ModelRequest,
    ModelResult,
    ModelRuntime,
    TokenUsage,
)
from app.models import ModelExecutionOptions, ProjectCreate
from app.prompts.models import PromptMessage, PromptPlan, ResponseContract


def json_request(project_id: str, secret: str = "author-secret") -> ModelRequest:
    return ModelRequest(
        prompt=PromptPlan(
            prompt_id="test.structured",
            prompt_version="1.0.0",
            use_case="runtime_test",
            messages=(PromptMessage(role="user", content=secret),),
            response_contract=ResponseContract(
                media_type="application/json",
                schema_name="test.object.v1",
                schema_version="1",
                json_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            ),
        ),
        metadata={"project_id": project_id},
    )


def profile(profile_id: str, provider: str, fallbacks=()) -> ModelProfile:
    return ModelProfile(
        id=profile_id,
        label=profile_id,
        provider_id=provider,
        model_id=f"{provider}/model",
        capabilities=ModelCapabilities(
            json_mode=True,
            json_schema=True,
            temperature=True,
            context_window_tokens=100_000,
            max_completion_tokens=10_000,
        ),
        fallback_profile_ids=tuple(fallbacks),
    )


class ModelRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteWritingDataStore(Path(self.temp.name) / "runtime.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Resilient runtime", premise="Failures remain reviewable.")
        )

    def runtime(self, first: FakeModelGateway, second: FakeModelGateway | None = None):
        registry = ModelGatewayRegistry()
        registry.register("first", lambda _model: first)
        profiles = [profile("first.default", "first", ("second.default",))]
        if second is not None:
            registry.register("second", lambda _model: second)
            profiles.append(profile("second.default", "second"))
        return ModelRuntime(registry, ModelCatalog(tuple(profiles)), self.store)

    def test_delayed_timeout_falls_back_and_persists_attempt_timing_and_usage(self) -> None:
        first = FakeModelGateway(
            [
                FakeGatewayScenario(
                    ModelGatewayError(
                        "timeout", "Timed out safely.", provider_id="first", retryable=True
                    ),
                    delay_seconds=0.025,
                )
            ],
            provider_id="first",
        )
        second = FakeModelGateway(
            [
                FakeGatewayScenario(
                    ModelResult(
                        content='{"ok": true}',
                        provider_id="second",
                        model_id="second/model",
                        finish_reason="stop",
                        usage=TokenUsage(input_tokens=19, output_tokens=5),
                    ),
                    delay_seconds=0.015,
                )
            ],
            provider_id="second",
        )

        started = time.perf_counter()
        execution = self.runtime(first, second).execute(
            json_request(self.project.id),
            ModelExecutionOptions(model_profile="first.default"),
        )
        elapsed = time.perf_counter() - started

        self.assertGreaterEqual(elapsed, 0.035)
        self.assertEqual(execution.fallback_count, 1)
        self.assertEqual(execution.attempt_count, 2)
        run = self.store.get_generation_run(self.project.id, execution.generation_run_id)
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.status, "succeeded")
        self.assertEqual((run.input_tokens, run.output_tokens), (19, 5))
        self.assertEqual([attempt.error_code for attempt in run.attempts], ["timeout", ""])
        self.assertGreaterEqual(run.attempts[0].duration_ms, 20)
        self.assertGreaterEqual(run.attempts[1].duration_ms, 10)

    def test_invalid_json_is_repaired_once_on_the_same_model(self) -> None:
        gateway = FakeModelGateway(
            [
                FakeGatewayScenario("not-json", delay_seconds=0.01),
                FakeGatewayScenario('{"ok": true}', delay_seconds=0.01),
            ],
            provider_id="first",
        )
        execution = self.runtime(gateway).execute(
            json_request(self.project.id),
            ModelExecutionOptions(
                model_profile="first.default", allow_fallback=False, allow_repair=True
            ),
        )

        self.assertEqual(execution.validated_value, {"ok": True})
        self.assertEqual((execution.attempt_count, execution.repair_count), (2, 1))
        self.assertEqual(gateway.requests[1].prompt.prompt_id, "system.response-repair")
        repair_text = gateway.requests[1].prompt.messages[1].content
        self.assertIn("<invalid-model-output>", repair_text)
        self.assertIn("<response-contract>", repair_text)
        run = self.store.get_generation_run(self.project.id, execution.generation_run_id)
        assert run is not None
        self.assertEqual([item.attempt_kind for item in run.attempts], ["primary", "repair"])

    def test_failed_repair_then_cross_provider_fallback_succeeds(self) -> None:
        first = FakeModelGateway(
            ["bad-primary", "bad-repair"], provider_id="first"
        )
        second = FakeModelGateway(['{"ok": true}'], provider_id="second")

        execution = self.runtime(first, second).execute(
            json_request(self.project.id),
            ModelExecutionOptions(model_profile="first.default"),
        )

        self.assertEqual((execution.attempt_count, execution.repair_count), (3, 1))
        self.assertEqual(execution.fallback_count, 1)
        run = self.store.get_generation_run(self.project.id, execution.generation_run_id)
        assert run is not None
        self.assertEqual(
            [(item.attempt_kind, item.provider, item.status) for item in run.attempts],
            [
                ("primary", "first", "failed"),
                ("repair", "first", "failed"),
                ("fallback", "second", "succeeded"),
            ],
        )

    def test_authentication_failure_does_not_fallback_and_failure_is_persisted(self) -> None:
        first = FakeModelGateway(
            [ModelGatewayError("authentication", "Authentication failed.", provider_id="first")],
            provider_id="first",
        )
        second = FakeModelGateway(['{"ok": true}'], provider_id="second")

        with self.assertRaises(ModelGatewayError) as raised:
            self.runtime(first, second).execute(
                json_request(self.project.id),
                ModelExecutionOptions(model_profile="first.default"),
            )

        self.assertEqual(raised.exception.code, "authentication")
        self.assertEqual(second.requests, [])
        runs = self.store.list_generation_runs(self.project.id)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "failed")
        self.assertEqual(runs[0].attempt_count, 1)

    def test_persistence_contains_metadata_only_and_survives_reopen(self) -> None:
        gateway = FakeModelGateway(['{"ok": true}'], provider_id="first")
        execution = self.runtime(gateway).execute(
            json_request(self.project.id, "do-not-persist-author-text"),
            ModelExecutionOptions(model_profile="first.default", allow_fallback=False),
        )
        with self.store.connect() as connection:
            stored = repr(
                connection.execute("SELECT * FROM generation_runs").fetchall()
                + connection.execute("SELECT * FROM generation_attempts").fetchall()
            )
        self.assertNotIn("do-not-persist-author-text", stored)
        self.assertNotIn('{"ok": true}', stored)

        reopened = SQLiteWritingDataStore(Path(self.temp.name) / "runtime.db")
        run = reopened.get_generation_run(self.project.id, execution.generation_run_id)
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.attempt_count, 1)


if __name__ == "__main__":
    unittest.main()
