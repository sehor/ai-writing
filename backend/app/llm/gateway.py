"""Provider-neutral model gateway contracts."""

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol

from app.prompts.models import PromptPlan


ModelErrorCode = Literal[
    "not_configured",
    "configuration",
    "sdk_unavailable",
    "authentication",
    "rate_limit",
    "timeout",
    "unavailable",
    "context_overflow",
    "output_truncated",
    "empty_response",
    "invalid_response",
    "execution",
]


@dataclass(frozen=True, slots=True)
class GenerationPolicy:
    temperature: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ModelRequest:
    prompt: PromptPlan
    policy: GenerationPolicy = field(default_factory=GenerationPolicy)
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelResult:
    content: str
    provider_id: str
    model_id: str
    request_id: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelCompletion:
    request: ModelRequest
    result: ModelResult


@dataclass(frozen=True, slots=True)
class GatewayDescriptor:
    provider_id: str
    model_id: str
    base_url: str = ""


class ModelGatewayError(RuntimeError):
    """Safe, stable error raised at the external model boundary."""

    def __init__(
        self,
        code: ModelErrorCode,
        safe_message: str,
        *,
        provider_id: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.provider_id = provider_id
        self.retryable = retryable
        self.trace: list[Any] = []

    @property
    def is_configuration_error(self) -> bool:
        return self.code in {"not_configured", "configuration", "sdk_unavailable"}


class ModelGateway(Protocol):
    provider_id: str

    def complete(self, request: ModelRequest) -> ModelResult: ...

    def describe(self) -> GatewayDescriptor: ...


def add_model_call_details(
    details: dict[str, object],
    request: ModelRequest,
    result: ModelResult,
) -> None:
    """Add allowlisted model metadata to an existing structured log event."""
    details.update(
        {
            "prompt_id": request.prompt.prompt_id,
            "prompt_version": request.prompt.prompt_version,
            "schema_name": request.prompt.response_contract.schema_name,
            "schema_version": request.prompt.response_contract.schema_version,
            "model": result.model_id,
            "finish_reason": result.finish_reason or "",
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
        }
    )
