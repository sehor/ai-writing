from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain_models.model import ModelExecutionOptions, WorkflowAgentTrace

SnowflakeRevisionSource = Literal["human", "ai", "legacy", "import", "restore", "derived"]


SnowflakeRevisionStatus = Literal[
    "draft", "pending_review", "accepted", "rejected", "superseded", "legacy_draft"
]


SnowflakeHeadState = Literal["missing", "approved", "stale", "skipped"]


SnowflakeRecordState = Literal["draft", "pending_review", "approved", "stale"]


SnowflakeDecision = Literal["accepted", "rejected"]


ValidationSeverity = Literal["warning", "critical"]


ValidationStatus = Literal["passed", "warnings", "failed", "skipped"]


class SnowflakeStep(BaseModel):
    number: int = Field(ge=1, le=10)
    title: str
    artifact: str
    description: str
    dependencies: list[int] = Field(default_factory=list)
    optional: bool = False
    schema_version: int = Field(default=1, ge=1)
    validator_name: str = "markdown_projection"
    virtual: bool = False


class SnowflakeArtifactRevisionPatch(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=200000)
    structured_payload: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def normalize_optional_revision_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class SnowflakeManuscriptProgress(BaseModel):
    project_id: str
    total_scene_contracts: int = Field(ge=0)
    pending_manuscript_proposals: int = Field(ge=0)
    accepted_latest_revisions: int = Field(ge=0)
    stale_scene_count: int = Field(ge=0)
    completion_percent: int = Field(ge=0, le=100)
    complete: bool


class SnowflakeGenerationCreate(ModelExecutionOptions):
    step_number: int = Field(ge=1, le=9)
    instruction: str = Field(min_length=1, max_length=4000)
    base_revision_id: str = Field(default="", max_length=160)
    target_record_ids: list[str] = Field(default_factory=list, max_length=200)
    generation_mode: Literal["replace", "record_set", "continue", "selection"] = "replace"
    previous_artifacts_context_chars: int = Field(default=64000, ge=1000, le=400000)

    @field_validator("instruction")
    @classmethod
    def normalize_instruction(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_generation_scope(self):
        if len(self.target_record_ids) != len(set(self.target_record_ids)):
            raise ValueError("Target record IDs must be unique.")
        if self.target_record_ids and self.step_number < 6:
            raise ValueError("Target record IDs are available only for Snowflake steps 6–9.")
        if (
            self.step_number >= 6
            and self.generation_mode in {"selection", "continue"}
            and not self.target_record_ids
        ):
            raise ValueError("This generation mode requires at least one target record ID.")
        if self.step_number not in {6, 7, 8, 9} and self.generation_mode == "record_set":
            raise ValueError("Record-set generation is available only for Snowflake steps 6–9.")
        return self


class SnowflakeGenerationRequest(ModelExecutionOptions):
    project_id: str = Field(min_length=1, max_length=120)
    step_number: int = Field(ge=1, le=10)
    user_input: str = Field(min_length=1, max_length=4000)
    base_revision_id: str = Field(default="", max_length=160)
    target_record_ids: list[str] = Field(default_factory=list, max_length=200)
    target_records: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    generation_mode: Literal["replace", "record_set", "continue", "selection"] = "replace"
    previous_artifacts_context_chars: int = Field(default=64000, ge=1000, le=400000)

    @field_validator("project_id", "user_input")
    @classmethod
    def normalize_generation_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_generation_scope(self):
        if len(self.target_record_ids) != len(set(self.target_record_ids)):
            raise ValueError("Target record IDs must be unique.")
        if self.target_record_ids and self.step_number < 6:
            raise ValueError("Target record IDs are available only for Snowflake steps 6–9.")
        if (
            self.step_number in {6, 7, 8, 9}
            and self.generation_mode in {"selection", "continue"}
            and not self.target_record_ids
        ):
            raise ValueError("This generation mode requires at least one target record ID.")
        if self.step_number not in {6, 7, 8, 9} and self.generation_mode == "record_set":
            raise ValueError("Record-set generation is available only for Snowflake steps 6–9.")
        return self


class SnowflakeGeneratedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any]


class SnowflakeArtifactUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class SnowflakeArtifact(BaseModel):
    project_id: str
    step_number: int = Field(ge=1, le=10)
    artifact: str
    content: str


class SnowflakeArtifactRevisionCreate(BaseModel):
    step_number: int = Field(ge=1, le=10)
    content: str = Field(min_length=1, max_length=200000)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1)
    parent_revision_id: str = Field(default="", max_length=160)
    base_head_revision_id: str = Field(default="", max_length=160)
    source: SnowflakeRevisionSource = "human"

    @field_validator("content")
    @classmethod
    def normalize_revision_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class SnowflakeArtifactRevision(BaseModel):
    id: str
    project_id: str
    step_number: int = Field(ge=1, le=10)
    artifact_type: str
    revision_no: int = Field(ge=1)
    source: SnowflakeRevisionSource
    status: SnowflakeRevisionStatus
    content: str
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(ge=1)
    parent_revision_id: str = ""
    base_head_revision_id: str = ""
    upstream_snapshot: dict[str, str] = Field(default_factory=dict)
    review_reason: str = ""
    created_at: str
    reviewed_at: str = ""


class SnowflakeArtifactHead(BaseModel):
    project_id: str
    step_number: int = Field(ge=1, le=10)
    accepted_revision_id: str = ""
    state: SnowflakeHeadState = "missing"
    stale_reason: str = ""
    stale_trigger_revision_id: str = ""


class SnowflakeRecordRevisionCreate(BaseModel):
    step_number: int = Field(ge=6, le=9)
    record_id: str = Field(min_length=1, max_length=160)
    position: int = Field(default=1, ge=1, le=100000)
    payload: dict[str, Any]
    base_revision_id: str = Field(default="", max_length=160)
    source: SnowflakeRevisionSource = "human"

    @field_validator("record_id")
    @classmethod
    def normalize_record_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank.")
        return value


class SnowflakeRecordRevision(BaseModel):
    id: str
    project_id: str
    step_number: int = Field(ge=6, le=9)
    record_id: str
    position: int = Field(ge=1)
    revision_no: int = Field(ge=1)
    source: SnowflakeRevisionSource
    status: SnowflakeRevisionStatus
    payload: dict[str, Any]
    base_revision_id: str = ""
    review_reason: str = ""
    created_at: str
    reviewed_at: str = ""


class SnowflakeRecordHead(BaseModel):
    project_id: str
    step_number: int = Field(ge=6, le=9)
    record_id: str
    accepted_revision_id: str = ""
    state: SnowflakeRecordState = "draft"


class SnowflakeRecordDecisionRequest(BaseModel):
    decision: SnowflakeDecision
    expected_revision_id: str = Field(default="", max_length=160)
    review_reason: str = Field(default="", max_length=2000)


class SnowflakeRevisionDecisionRequest(BaseModel):
    decision: SnowflakeDecision
    expected_head_revision_id: str = Field(default="", max_length=160)
    review_reason: str = Field(default="", max_length=2000)


class SnowflakeGeneratedRecordSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[SnowflakeGeneratedRecord] = Field(min_length=1, max_length=200)


class SnowflakeValidationFinding(BaseModel):
    code: str
    severity: ValidationSeverity
    message: str
    path: str = ""
    evidence: str = ""


class SnowflakeStepState(BaseModel):
    step: SnowflakeStep
    state: SnowflakeHeadState = "missing"
    accepted_revision: SnowflakeArtifactRevision | None = None
    pending_count: int = Field(default=0, ge=0)
    stale_reason: str = ""
    stale_trigger_revision_id: str = ""


class SnowflakeRevisionPage(BaseModel):
    data: list[SnowflakeArtifactRevision] = Field(default_factory=list)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class SnowflakeRecordPage(BaseModel):
    data: list[SnowflakeRecordRevision] = Field(default_factory=list)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class SnowflakeRecordDecisionResponse(BaseModel):
    revision: SnowflakeRecordRevision
    head: SnowflakeRecordHead


class SnowflakeValidationReport(BaseModel):
    step_number: int = Field(ge=1, le=10)
    status: ValidationStatus
    findings: list[SnowflakeValidationFinding] = Field(default_factory=list)


class SnowflakeRevisionDecisionResponse(BaseModel):
    revision: SnowflakeArtifactRevision
    head: SnowflakeArtifactHead
    affected_steps: list[int] = Field(default_factory=list)
    outbox_job_id: str = ""
    validation_report: SnowflakeValidationReport | None = None


class SnowflakeGenerationResponse(BaseModel):
    project_id: str
    step_number: int = Field(ge=1, le=10)
    artifact: str
    content: str
    workflow_trace: list[WorkflowAgentTrace] = Field(default_factory=list)
    revision: SnowflakeArtifactRevision | None = None
    record_revisions: list[SnowflakeRecordRevision] = Field(default_factory=list)
    validation_report: SnowflakeValidationReport | None = None
