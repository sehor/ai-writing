"""Provider-neutral prompt and response contracts."""

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


PromptRole = Literal["system", "user", "assistant"]
ResponseMediaType = Literal["application/json", "text/markdown"]


@dataclass(frozen=True, slots=True)
class PromptMessage:
    role: PromptRole
    content: str


@dataclass(frozen=True, slots=True)
class ResponseContract:
    media_type: ResponseMediaType
    schema_name: str
    schema_version: str
    json_schema: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PromptPlan:
    prompt_id: str
    prompt_version: str
    use_case: str
    messages: tuple[PromptMessage, ...]
    response_contract: ResponseContract
    metadata: Mapping[str, str] = field(default_factory=dict)
