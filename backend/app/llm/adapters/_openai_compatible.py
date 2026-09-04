"""Shared transport helpers for OpenAI-compatible provider adapters."""

from typing import Any

from app.llm.gateway import ModelGatewayError, TokenUsage


def create_openai_client(api_key: str, base_url: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelGatewayError(
            "sdk_unavailable",
            "The OpenAI-compatible SDK is not installed.",
        ) from exc
    return OpenAI(api_key=api_key, base_url=base_url)


def map_openai_compatible_exception(
    exc: Exception,
    provider_id: str,
) -> ModelGatewayError:
    name = type(exc).__name__
    lowered = str(exc).lower()
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ModelGatewayError(
            "authentication",
            "Model provider authentication failed.",
            provider_id=provider_id,
        )
    if name == "RateLimitError":
        return ModelGatewayError(
            "rate_limit",
            "Model provider rate limit was reached.",
            provider_id=provider_id,
            retryable=True,
        )
    if name in {"APITimeoutError", "TimeoutError"}:
        return ModelGatewayError(
            "timeout",
            "Model provider request timed out.",
            provider_id=provider_id,
            retryable=True,
        )
    if name in {"APIConnectionError", "InternalServerError", "ServiceUnavailableError"}:
        return ModelGatewayError(
            "unavailable",
            "Model provider is temporarily unavailable.",
            provider_id=provider_id,
            retryable=True,
        )
    if name == "BadRequestError" and ("context" in lowered or "token" in lowered):
        return ModelGatewayError(
            "context_overflow",
            "Model context or output token limit was exceeded.",
            provider_id=provider_id,
        )
    return ModelGatewayError(
        "execution",
        "Model provider request failed.",
        provider_id=provider_id,
    )


def extract_usage(usage: Any) -> TokenUsage:
    data = usage.model_dump() if hasattr(usage, "model_dump") else usage
    if not isinstance(data, dict):
        return TokenUsage()
    return TokenUsage(
        input_tokens=_optional_int(data.get("prompt_tokens")),
        output_tokens=_optional_int(data.get("completion_tokens")),
        cached_input_tokens=_optional_int(data.get("prompt_cache_hit_tokens")),
    )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
