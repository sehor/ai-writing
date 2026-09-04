from types import SimpleNamespace
import unittest

from app.llm import (
    DeepSeekAdapter,
    DeepSeekSettings,
    FakeModelGateway,
    GenerationPolicy,
    ModelGatewayError,
    ModelRequest,
    ModelResult,
    TokenUsage,
    OpenRouterAdapter,
    OpenRouterSettings,
    add_model_call_details,
)
from app.prompts import compile_reference_prompt
from app.prompts.models import PromptMessage, PromptPlan, ResponseContract


class CapturingCompletions:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


def fake_client(completions: CapturingCompletions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def fake_response(*, content="draft", finish_reason="stop"):
    return SimpleNamespace(
        id="request-1",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage={
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "prompt_cache_hit_tokens": 3,
        },
    )


class DeepSeekAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = DeepSeekSettings(
            api_key="secret-key",
            base_url="https://models.invalid",
            model="test-model",
            temperature=0.7,
            max_tokens=2400,
        )
        self.plan = compile_reference_prompt("private author context")

    def test_maps_provider_request_and_response_without_leaking_sdk_types(self) -> None:
        completions = CapturingCompletions(fake_response())
        adapter = DeepSeekAdapter(
            self.settings,
            client_factory=lambda _key, _url: fake_client(completions),
        )
        request = ModelRequest(
            prompt=self.plan,
            policy=GenerationPolicy(temperature=0.2, max_output_tokens=512, timeout_seconds=12),
        )

        result = adapter.complete(request)

        self.assertEqual(result.provider_id, "deepseek")
        self.assertEqual(result.model_id, "test-model")
        self.assertEqual(result.request_id, "request-1")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage, TokenUsage(11, 7, 3))
        self.assertEqual(completions.kwargs["temperature"], 0.2)
        self.assertEqual(completions.kwargs["max_tokens"], 512)
        self.assertEqual(completions.kwargs["timeout"], 12)
        self.assertEqual(completions.kwargs["messages"][0]["role"], "system")

    def test_truncated_and_empty_responses_fail_closed(self) -> None:
        for response, code in [
            (fake_response(finish_reason="length"), "output_truncated"),
            (fake_response(content=""), "empty_response"),
        ]:
            adapter = DeepSeekAdapter(
                self.settings,
                client_factory=lambda _key, _url, response=response: fake_client(
                    CapturingCompletions(response)
                ),
            )
            with self.assertRaises(ModelGatewayError) as raised:
                adapter.complete(ModelRequest(prompt=self.plan))
            self.assertEqual(raised.exception.code, code)

    def test_provider_error_is_normalized_without_raw_message(self) -> None:
        AuthenticationError = type("AuthenticationError", (Exception,), {})
        completions = CapturingCompletions(error=AuthenticationError("secret-key rejected"))
        adapter = DeepSeekAdapter(
            self.settings,
            client_factory=lambda _key, _url: fake_client(completions),
        )
        with self.assertRaises(ModelGatewayError) as raised:
            adapter.complete(ModelRequest(prompt=self.plan))
        self.assertEqual(raised.exception.code, "authentication")
        self.assertNotIn("secret-key", raised.exception.safe_message)

    def test_retryable_and_limit_errors_are_normalized(self) -> None:
        cases = [
            ("RateLimitError", "quota response", "rate_limit", True),
            ("APITimeoutError", "socket timed out", "timeout", True),
            ("APIConnectionError", "host unavailable", "unavailable", True),
            ("BadRequestError", "maximum context token limit", "context_overflow", False),
        ]
        for class_name, raw_message, code, retryable in cases:
            with self.subTest(code=code):
                ProviderError = type(class_name, (Exception,), {})
                adapter = DeepSeekAdapter(
                    self.settings,
                    client_factory=lambda _key, _url, error=ProviderError(raw_message): fake_client(
                        CapturingCompletions(error=error)
                    ),
                )
                with self.assertRaises(ModelGatewayError) as raised:
                    adapter.complete(ModelRequest(prompt=self.plan))
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(raised.exception.retryable, retryable)
                self.assertNotIn(raw_message, raised.exception.safe_message)

    def test_observability_details_are_allowlisted(self) -> None:
        request = ModelRequest(prompt=self.plan)
        result = ModelResult(
            content="private result",
            provider_id="deepseek",
            model_id="test-model",
            usage=TokenUsage(input_tokens=5, output_tokens=8),
        )
        details: dict[str, object] = {}
        add_model_call_details(details, request, result)
        serialized = repr(details)
        self.assertNotIn("secret-key", serialized)
        self.assertNotIn("private author context", serialized)
        self.assertNotIn("private result", serialized)
        self.assertEqual(details["prompt_id"], "reference.suggestion")

    def test_fake_gateway_executes_the_same_prompt_plan_contract(self) -> None:
        gateway = FakeModelGateway(["result"])
        request = ModelRequest(prompt=self.plan)
        result = gateway.complete(request)
        self.assertIs(gateway.requests[0].prompt, self.plan)
        self.assertEqual(result.content, "result")


class OpenRouterAdapterTests(unittest.TestCase):
    def test_sends_model_selection_headers_and_native_json_schema(self) -> None:
        completions = CapturingCompletions(fake_response(content='{"ok":true}'))
        adapter = OpenRouterAdapter(
            OpenRouterSettings(
                api_key="test-only-key",
                model="vendor/selected-model",
                site_url="https://studio.invalid",
                app_name="Studio Tests",
            ),
            client_factory=lambda _key, _url: fake_client(completions),
        )
        plan = PromptPlan(
            prompt_id="test.json",
            prompt_version="1.0.0",
            use_case="test",
            messages=(PromptMessage(role="user", content="private"),),
            response_contract=ResponseContract(
                media_type="application/json",
                schema_name="test.object.v1",
                schema_version="1",
                json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            ),
        )

        result = adapter.complete(ModelRequest(prompt=plan))

        self.assertEqual(result.provider_id, "openrouter")
        self.assertEqual(completions.kwargs["model"], "vendor/selected-model")
        self.assertEqual(
            completions.kwargs["extra_headers"],
            {"HTTP-Referer": "https://studio.invalid", "X-Title": "Studio Tests"},
        )
        response_format = completions.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertEqual(response_format["json_schema"]["name"], "test_object_v1")

    def test_openrouter_normalizes_rate_limit_and_truncation(self) -> None:
        RateLimitError = type("RateLimitError", (Exception,), {})
        cases = [
            (CapturingCompletions(error=RateLimitError("quota details")), "rate_limit"),
            (CapturingCompletions(fake_response(finish_reason="length")), "output_truncated"),
        ]
        for completions, expected in cases:
            with self.subTest(expected=expected):
                adapter = OpenRouterAdapter(
                    OpenRouterSettings(api_key="test-key"),
                    client_factory=lambda _key, _url, c=completions: fake_client(c),
                )
                with self.assertRaises(ModelGatewayError) as raised:
                    adapter.complete(ModelRequest(prompt=compile_reference_prompt("private")))
                self.assertEqual(raised.exception.code, expected)
                self.assertNotIn("quota details", raised.exception.safe_message)


if __name__ == "__main__":
    unittest.main()
