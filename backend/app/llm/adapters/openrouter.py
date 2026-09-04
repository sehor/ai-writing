"""OpenRouter adapter using its OpenAI-compatible chat-completions API."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.llm.adapters._openai_compatible import (
    create_openai_client,
    extract_usage,
    map_openai_compatible_exception,
)
from app.llm.gateway import (
    GatewayDescriptor,
    ModelGatewayError,
    ModelRequest,
    ModelResult,
)


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "google/gemini-3.8-flash"


@dataclass(frozen=True, slots=True)
class OpenRouterSettings:
    api_key: str
    model: str = DEFAULT_OPENROUTER_MODEL
    base_url: str = DEFAULT_OPENROUTER_BASE_URL
    site_url: str = ""
    app_name: str = "AI Writing Studio"
    temperature: float = 0.7
    max_tokens: int = 2400

    @classmethod
    def from_env(cls, model_id: str | None = None) -> "OpenRouterSettings | None":
        load_project_env()
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0.7"))
            max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "2400"))
        except ValueError as exc:
            raise ModelGatewayError(
                "configuration",
                "OpenRouter generation settings are invalid.",
                provider_id="openrouter",
            ) from exc
        if max_tokens <= 0:
            raise ModelGatewayError(
                "configuration",
                "OpenRouter max tokens must be positive.",
                provider_id="openrouter",
            )
        return cls(
            api_key=api_key,
            model=model_id
            or os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
            or DEFAULT_OPENROUTER_MODEL,
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip()
            or DEFAULT_OPENROUTER_BASE_URL,
            site_url=os.getenv("OPENROUTER_SITE_URL", "").strip(),
            app_name=os.getenv("OPENROUTER_APP_NAME", "AI Writing Studio").strip()
            or "AI Writing Studio",
            temperature=temperature,
            max_tokens=max_tokens,
        )


class OpenRouterAdapter:
    provider_id = "openrouter"

    def __init__(
        self,
        settings: OpenRouterSettings,
        client_factory: Callable[[str, str], Any] | None = None,
        *,
        native_json_schema: bool = True,
    ) -> None:
        self.settings = settings
        self.native_json_schema = native_json_schema
        self._client_factory = client_factory or create_openai_client
        self._client: Any | None = None

    def describe(self) -> GatewayDescriptor:
        return GatewayDescriptor(
            provider_id=self.provider_id,
            model_id=self.settings.model,
            base_url=self.settings.base_url,
        )

    def complete(self, request: ModelRequest) -> ModelResult:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.prompt.messages
            ],
            "temperature": (
                request.policy.temperature
                if request.policy.temperature is not None
                else self.settings.temperature
            ),
            "max_tokens": (
                request.policy.max_output_tokens
                if request.policy.max_output_tokens is not None
                else self.settings.max_tokens
            ),
        }
        if request.policy.timeout_seconds is not None:
            kwargs["timeout"] = request.policy.timeout_seconds
        headers = self._headers()
        if headers:
            kwargs["extra_headers"] = headers
        contract = request.prompt.response_contract
        if self.native_json_schema and contract.json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(contract.schema_name),
                    "strict": True,
                    "schema": dict(contract.json_schema),
                },
            }
        elif contract.media_type == "application/json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except ModelGatewayError:
            raise
        except Exception as exc:
            raise map_openai_compatible_exception(exc, self.provider_id) from exc

        choice = response.choices[0] if getattr(response, "choices", None) else None
        finish_reason = getattr(choice, "finish_reason", None) if choice else None
        if finish_reason == "length":
            raise ModelGatewayError(
                "output_truncated",
                "Model output was truncated before completion.",
                provider_id=self.provider_id,
            )
        content = getattr(getattr(choice, "message", None), "content", None) if choice else None
        if not isinstance(content, str) or not content.strip():
            raise ModelGatewayError(
                "empty_response",
                "Model returned no content.",
                provider_id=self.provider_id,
            )
        return ModelResult(
            content=content.strip(),
            provider_id=self.provider_id,
            model_id=str(getattr(response, "model", "") or self.settings.model),
            request_id=str(getattr(response, "id", "") or "") or None,
            finish_reason=str(finish_reason) if finish_reason is not None else None,
            usage=extract_usage(getattr(response, "usage", None)),
        )

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(self.settings.api_key, self.settings.base_url)
        return self._client

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.site_url:
            headers["HTTP-Referer"] = self.settings.site_url
        if self.settings.app_name:
            headers["X-Title"] = self.settings.app_name
        return headers


def create_openrouter_gateway(model_id: str | None = None) -> OpenRouterAdapter | None:
    settings = OpenRouterSettings.from_env(model_id)
    return OpenRouterAdapter(settings) if settings is not None else None


def _schema_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
    return normalized[:64] or "response"


def load_project_env() -> None:
    for env_path in candidate_env_paths():
        if env_path.is_file():
            load_env_file(env_path)
            return


def candidate_env_paths() -> list[Path]:
    paths: list[Path] = []
    for start in [Path.cwd(), Path(__file__).resolve()]:
        for directory in [start, *start.parents]:
            candidate = directory / ".env"
            if candidate not in paths:
                paths.append(candidate)
    return paths


def load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


__all__ = [
    "OpenRouterAdapter",
    "OpenRouterSettings",
    "create_openrouter_gateway",
]
