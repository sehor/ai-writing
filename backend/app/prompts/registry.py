"""Static in-process registry for versioned prompt definitions."""

from dataclasses import dataclass

from app.prompts.models import ResponseContract


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    prompt_id: str
    version: str
    use_case: str
    response_contract: ResponseContract


class PromptRegistry:
    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], PromptDefinition] = {}
        self._defaults: dict[str, str] = {}

    def register(self, definition: PromptDefinition, *, make_default: bool = True) -> None:
        key = (definition.prompt_id, definition.version)
        if key in self._definitions:
            raise ValueError(
                f"Prompt '{definition.prompt_id}' version '{definition.version}' is already registered."
            )
        self._definitions[key] = definition
        if make_default or definition.prompt_id not in self._defaults:
            self._defaults[definition.prompt_id] = definition.version

    def get(self, prompt_id: str, version: str | None = None) -> PromptDefinition:
        resolved_version = version or self._defaults.get(prompt_id)
        if resolved_version is None:
            raise LookupError(f"Prompt '{prompt_id}' is not registered.")
        try:
            return self._definitions[(prompt_id, resolved_version)]
        except KeyError as exc:
            raise LookupError(
                f"Prompt '{prompt_id}' version '{resolved_version}' is not registered."
            ) from exc

    def definitions(self) -> tuple[PromptDefinition, ...]:
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions, key=lambda item: (item[0], item[1]))
        )


default_prompt_registry = PromptRegistry()

