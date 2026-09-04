"""OpenAI-compatible DeepSeek model gateway adapter."""

import os
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


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True, slots=True)
class DeepSeekSettings:
    api_key: str
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    temperature: float = 0.7
    max_tokens: int = 2400

    @classmethod
    def from_env(cls) -> "DeepSeekSettings | None":
        load_project_env()
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7"))
            max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "2400"))
        except ValueError as exc:
            raise ModelGatewayError(
                "configuration",
                "DeepSeek generation settings are invalid.",
                provider_id="deepseek",
            ) from exc
        if max_tokens <= 0:
            raise ModelGatewayError(
                "configuration",
                "DeepSeek max tokens must be positive.",
                provider_id="deepseek",
            )
        return cls(
            api_key=api_key,
            base_url=os.getenv(
                "DEEPSEEK_BASE_URL_FOR_OPENAI",
                os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            ).strip()
            or DEFAULT_DEEPSEEK_BASE_URL,
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip()
            or DEFAULT_DEEPSEEK_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
        )


class DeepSeekAdapter:
    provider_id = "deepseek"

    def __init__(
        self,
        settings: DeepSeekSettings,
        client_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.settings = settings
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
            model_id=self.settings.model,
            request_id=str(getattr(response, "id", "") or "") or None,
            finish_reason=str(finish_reason) if finish_reason is not None else None,
            usage=extract_usage(getattr(response, "usage", None)),
        )

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(self.settings.api_key, self.settings.base_url)
        return self._client


def create_deepseek_gateway(model_id: str | None = None) -> DeepSeekAdapter | None:
    settings = DeepSeekSettings.from_env()
    if settings is not None and model_id:
        settings = DeepSeekSettings(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=model_id,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
    return DeepSeekAdapter(settings) if settings is not None else None


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
