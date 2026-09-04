"""P2-08: structured observability guarantees."""

import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.llm import FakeModelGateway, ModelGatewayRegistry
from app.observability import bind_request_id, log_event, new_request_id, timed_operation


def _payload(captured, index: int) -> dict:
    """assertLogs wraps our raw JSON line in its own 'LEVEL:name:' prefix."""
    line = captured.output[index]
    return json.loads(line[line.index("{") :])


class LogEventTests(unittest.TestCase):
    def test_log_event_emits_parseable_json_with_request_id(self) -> None:
        bind_request_id("req-123")
        with self.assertLogs("ai_writing.ops", level="INFO") as captured:
            log_event(
                "outbox_job",
                operation="llm_wiki_ingest",
                project_id="p1",
                aggregate_id="manuscript_revision:r1",
                duration_ms=12.5,
                result="succeeded",
                error_code="",
            )
        payload = _payload(captured, 0)
        self.assertEqual(payload["event"], "outbox_job")
        self.assertEqual(payload["request_id"], "req-123")
        self.assertEqual(payload["operation"], "llm_wiki_ingest")
        self.assertEqual(payload["result"], "succeeded")
        # empty fields are omitted entirely
        self.assertNotIn("error_code", payload)

    def test_timed_operation_logs_ok_and_error_paths(self) -> None:
        with self.assertLogs("ai_writing.ops", level="INFO") as captured:
            with timed_operation(
                "provider_call", operation="generate_manuscript", provider="local"
            ):
                pass
            with self.assertRaises(RuntimeError):
                with timed_operation(
                    "provider_call", operation="generate_snowflake", provider="deepseek"
                ):
                    raise RuntimeError("boom")
        ok_payload = _payload(captured, 0)
        self.assertEqual(ok_payload["result"], "ok")
        self.assertEqual(ok_payload["provider"], "local")
        self.assertIsInstance(ok_payload["duration_ms"], float)
        error_payload = _payload(captured, 1)
        self.assertEqual(error_payload["result"], "error")
        self.assertEqual(error_payload["error_code"], "RuntimeError")

    def test_request_ids_are_unique_enough_for_correlation(self) -> None:
        ids = {new_request_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)


class MiddlewareTests(unittest.TestCase):
    def _app(self) -> FastAPI:
        from app.main import observability_middleware

        app = FastAPI()
        app.middleware("http")(observability_middleware)

        @app.get("/api/projects/{project_id}/things")
        def things(project_id: str):
            return {"project_id": project_id}

        return app

    def test_response_carries_request_id_and_access_event_is_logged(self) -> None:
        client = TestClient(self._app())
        with self.assertLogs("ai_writing.ops", level="INFO") as captured:
            response = client.get("/api/projects/abc/things")
        request_id = response.headers["x-request-id"]
        self.assertTrue(request_id)
        payload = _payload(captured, -1)
        self.assertEqual(payload["event"], "http_request")
        self.assertEqual(payload["request_id"], request_id)
        self.assertEqual(payload["operation"], "GET /api/projects/{project_id}/things")
        self.assertEqual(payload["project_id"], "abc")
        self.assertEqual(payload["status"], 200)
        self.assertEqual(payload["result"], "ok")

    def test_error_status_marks_result_and_error_code(self) -> None:
        from fastapi import HTTPException

        from app.main import observability_middleware

        app = FastAPI()
        app.middleware("http")(observability_middleware)

        @app.get("/broken")
        def broken():
            raise HTTPException(status_code=404)

        client = TestClient(app, raise_server_exceptions=False)
        with self.assertLogs("ai_writing.ops", level="INFO") as captured:
            client.get("/broken")
        payload = _payload(captured, -1)
        self.assertEqual(payload["status"], 404)
        self.assertEqual(payload["result"], "client_error")
        self.assertEqual(payload["error_code"], "http_404")


class RegistryContractTests(unittest.TestCase):
    def test_create_returns_concrete_gateway_instance(self) -> None:
        # P2-08 instrumentation lives at service call sites (timed_operation),
        # NOT by wrapping the gateway: callers and tests rely on the concrete
        # type coming out of the registry.
        registry = ModelGatewayRegistry()
        gateway = FakeModelGateway()
        registry.register("fake", lambda: gateway)
        self.assertIs(registry.create("fake"), gateway)
        self.assertEqual(gateway.provider_id, "fake")


if __name__ == "__main__":
    unittest.main()
