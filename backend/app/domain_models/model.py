from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkflowRuntimeType = Literal[
    "local_deterministic",
    "provider_deepseek",
    "provider_openrouter",
]


WorkflowRuntimeKind = Literal["local_deterministic", "model_gateway"]


GenerationRunStatus = Literal["running", "succeeded", "failed"]


GenerationAttemptStatus = Literal["succeeded", "failed"]


GenerationAttemptKind = Literal["primary", "repair", "fallback"]


class ModelExecutionOptions(BaseModel):
    model_profile: str = Field(default="", max_length=120, pattern=r"^[a-z0-9._-]*$")
    allow_fallback: bool = True
    allow_repair: bool = True


class WorkflowAgentTrace(BaseModel):
    stage: str
    agent_name: str
    status: str
    finding_count: int = Field(default=0, ge=0)
    details: str = ""
    prompt_id: str = ""
    prompt_version: str = ""
    schema_name: str = ""
    schema_version: str = ""
    provider_id: str = ""
    model_id: str = ""
    finish_reason: str = ""
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    generation_run_id: str = ""
    attempt_count: int = Field(default=0, ge=0)
    repair_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)


class ModelCapabilitiesView(BaseModel):
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
    context_window_tokens: int = Field(default=0, ge=0)
    max_completion_tokens: int = Field(default=0, ge=0)


class GenerationRunCreate(BaseModel):
    id: str
    project_id: str
    use_case: str
    prompt_id: str
    prompt_version: str
    schema_name: str
    schema_version: str
    requested_profile_id: str = ""
    allow_fallback: bool = True
    allow_repair: bool = True
    created_at: str


class GenerationRunUpdate(BaseModel):
    status: Literal["succeeded", "failed"]
    final_profile_id: str = ""
    provider: str = ""
    model: str = ""
    error_code: str = ""
    safe_error: str = ""
    attempt_count: int = Field(default=0, ge=0)
    repair_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0, ge=0)
    completed_at: str


class ProviderGenerationRequest(ModelExecutionOptions):
    pass


class WorkflowRuntimeStatus(BaseModel):
    runtime: WorkflowRuntimeType
    runtime_kind: WorkflowRuntimeKind | None = None
    provider: str
    provider_configured: bool
    model: str = ""
    base_url: str = ""
    details: str = ""


class ModelProfileView(BaseModel):
    id: str
    label: str
    provider: str
    model: str
    configured: bool
    capabilities: ModelCapabilitiesView
    fallback_profile_ids: list[str] = Field(default_factory=list)


class GenerationAttemptCreate(BaseModel):
    attempt_index: int = Field(ge=1)
    attempt_kind: GenerationAttemptKind
    profile_id: str
    provider: str
    model: str
    status: GenerationAttemptStatus
    error_code: str = ""
    retryable: bool = False
    duration_ms: float = Field(default=0, ge=0)
    finish_reason: str = ""
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    created_at: str


class GenerationAttempt(GenerationAttemptCreate):
    id: str
    run_id: str


class GenerationRun(BaseModel):
    id: str
    project_id: str
    use_case: str
    prompt_id: str
    prompt_version: str
    schema_name: str
    schema_version: str
    requested_profile_id: str = ""
    final_profile_id: str = ""
    provider: str = ""
    model: str = ""
    status: GenerationRunStatus
    error_code: str = ""
    safe_error: str = ""
    allow_fallback: bool = True
    allow_repair: bool = True
    attempt_count: int = Field(default=0, ge=0)
    repair_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0, ge=0)
    created_at: str
    completed_at: str = ""
    attempts: list[GenerationAttempt] = Field(default_factory=list)
