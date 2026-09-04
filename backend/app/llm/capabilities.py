"""Curated, provider-neutral model capability matrix."""

from dataclasses import dataclass

from app.llm.gateway import ModelRequest


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    text_generation: bool = True
    json_mode: bool = False
    json_schema: bool = False
    temperature: bool = False
    max_output_tokens: bool = True
    timeout: bool = True
    seed: bool = False
    reasoning: bool = False
    tools: bool = False
    streaming: bool = False
    vision: bool = False
    usage_reporting: bool = True
    finish_reason: bool = True
    request_id: bool = True
    context_window_tokens: int = 0
    max_completion_tokens: int = 0

    def supports(self, request: ModelRequest) -> bool:
        requested_tokens = request.policy.max_output_tokens or 0
        if not self.text_generation:
            return False
        if self.max_completion_tokens and requested_tokens > self.max_completion_tokens:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: str
    label: str
    provider_id: str
    model_id: str
    capabilities: ModelCapabilities
    fallback_profile_ids: tuple[str, ...] = ()


class ModelCatalog:
    def __init__(self, profiles: tuple[ModelProfile, ...]) -> None:
        self._profiles = {profile.id: profile for profile in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("Model profile IDs must be unique.")

    def profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(self._profiles.values())

    def get(self, profile_id: str) -> ModelProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise LookupError(f"Unknown model profile '{profile_id}'.") from exc

    def candidates(
        self,
        requested_profile_id: str,
        *,
        allow_fallback: bool,
    ) -> tuple[ModelProfile, ...]:
        if requested_profile_id:
            primary = self.get(requested_profile_id)
            ids = [primary.id]
            if allow_fallback:
                ids.extend(primary.fallback_profile_ids)
        else:
            ids = [profile.id for profile in self._profiles.values()]
            if not allow_fallback:
                ids = ids[:1]
        seen: set[str] = set()
        result: list[ModelProfile] = []
        for profile_id in ids:
            if profile_id in seen or profile_id not in self._profiles:
                continue
            seen.add(profile_id)
            result.append(self._profiles[profile_id])
        return tuple(result)


OPENROUTER_GEMINI_CAPABILITIES = ModelCapabilities(
    json_mode=True,
    json_schema=True,
    temperature=True,
    seed=True,
    reasoning=True,
    tools=True,
    streaming=True,
    vision=True,
    context_window_tokens=1_048_576,
    max_completion_tokens=65_536,
)

OPENROUTER_CLAUDE_CAPABILITIES = ModelCapabilities(
    json_mode=True,
    json_schema=True,
    reasoning=True,
    tools=True,
    streaming=True,
    vision=True,
    context_window_tokens=1_000_000,
    max_completion_tokens=128_000,
)

DEEPSEEK_CAPABILITIES = ModelCapabilities(
    json_mode=True,
    temperature=True,
    streaming=True,
    context_window_tokens=128_000,
    max_completion_tokens=8_192,
)

default_model_catalog = ModelCatalog(
    (
        ModelProfile(
            id="deepseek.default",
            label="DeepSeek (configured default)",
            provider_id="deepseek",
            model_id="",
            capabilities=DEEPSEEK_CAPABILITIES,
            fallback_profile_ids=(
                "openrouter.gemini-3.8-flash",
                "openrouter.claude-fable-5.1",
            ),
        ),
        ModelProfile(
            id="openrouter.gemini-3.8-flash",
            label="OpenRouter · Gemini 3.8 Flash",
            provider_id="openrouter",
            model_id="google/gemini-3.8-flash",
            capabilities=OPENROUTER_GEMINI_CAPABILITIES,
            fallback_profile_ids=(
                "openrouter.claude-fable-5.1",
                "deepseek.default",
            ),
        ),
        ModelProfile(
            id="openrouter.claude-fable-5.1",
            label="OpenRouter · Claude Fable 5.1",
            provider_id="openrouter",
            model_id="anthropic/claude-fable-5.1",
            capabilities=OPENROUTER_CLAUDE_CAPABILITIES,
            fallback_profile_ids=(
                "openrouter.gemini-3.8-flash",
                "deepseek.default",
            ),
        ),
    )
)


__all__ = [
    "DEEPSEEK_CAPABILITIES",
    "ModelCapabilities",
    "ModelCatalog",
    "ModelProfile",
    "default_model_catalog",
]
