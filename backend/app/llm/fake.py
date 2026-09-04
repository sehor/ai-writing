"""Recording model gateway used by contract and workflow tests."""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from threading import Lock
from time import sleep

from app.llm.gateway import GatewayDescriptor, ModelGatewayError, ModelRequest, ModelResult


@dataclass(frozen=True, slots=True)
class FakeGatewayScenario:
    outcome: str | ModelResult | Exception
    delay_seconds: float = 0


class FakeModelGateway:
    provider_id = "fake"

    def __init__(
        self,
        responses: Iterable[str | ModelResult | Exception | FakeGatewayScenario] = (),
        *,
        provider_id: str = "fake",
        model_id: str = "fake-model",
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self.requests: list[ModelRequest] = []
        self._responses = deque(responses)
        self._lock = Lock()

    def queue(self, response: str | ModelResult | Exception | FakeGatewayScenario) -> None:
        with self._lock:
            self._responses.append(response)

    def complete(self, request: ModelRequest) -> ModelResult:
        with self._lock:
            self.requests.append(request)
            if not self._responses:
                raise ModelGatewayError(
                    "empty_response",
                    "Fake model gateway has no queued response.",
                    provider_id=self.provider_id,
                )
            response = self._responses.popleft()
        if isinstance(response, FakeGatewayScenario):
            if response.delay_seconds < 0:
                raise ValueError("Fake gateway delay cannot be negative.")
            sleep(response.delay_seconds)
            response = response.outcome
        if isinstance(response, Exception):
            raise response
        if isinstance(response, ModelResult):
            return response
        return ModelResult(content=response, provider_id=self.provider_id, model_id=self.model_id)

    def describe(self) -> GatewayDescriptor:
        return GatewayDescriptor(provider_id=self.provider_id, model_id=self.model_id)


__all__ = ["FakeGatewayScenario", "FakeModelGateway"]
