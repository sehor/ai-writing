from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "ai-writing-backend"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    premise: str = Field(min_length=1, max_length=500)

    @field_validator("title", "premise")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class ProjectSummary(BaseModel):
    id: str
    title: str
    premise: str
    current_step: int = Field(ge=1, le=10)


class SnowflakeStep(BaseModel):
    number: int = Field(ge=1, le=10)
    title: str
    artifact: str
    description: str


class SnowflakeGenerationRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    step_number: int = Field(ge=1, le=10)
    user_input: str = Field(min_length=1, max_length=4000)

    @field_validator("project_id", "user_input")
    @classmethod
    def normalize_generation_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class SnowflakeGenerationResponse(BaseModel):
    project_id: str
    step_number: int = Field(ge=1, le=10)
    artifact: str
    content: str
