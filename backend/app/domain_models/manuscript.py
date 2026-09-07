from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.snowflake.contracts import ManuscriptSceneDraftContract

ManuscriptProposalSource = Literal["scene_contract", "legacy_snowflake_import"]


ManuscriptProposalStatus = Literal["pending_review", "accepted", "rejected", "superseded"]


class ManuscriptChapterCreate(BaseModel):
    sequence: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=2000)

    @field_validator("title", "summary")
    @classmethod
    def normalize_chapter_text(cls, value: str) -> str:
        return value.strip()


class ChapterCompileResponse(BaseModel):
    project_id: str
    scene_id: str
    context: str
    draft: str
    checklist: list[str] = Field(default_factory=list)


class ManuscriptGenerationReview(BaseModel):
    """Immutable original model review material, separate from author edits."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    availability: Literal["structured", "legacy_prose_only"]
    generation_run_id: str = ""
    provider: str = ""
    model: str = ""
    material: ManuscriptSceneDraftContract | None = None

    @model_validator(mode="after")
    def validate_material_presence(self):
        if (self.availability == "structured") != (self.material is not None):
            raise ValueError("Structured review requires material; legacy output has none.")
        return self


class ManuscriptProposalAcceptance(BaseModel):
    """Author edits are committed without mutating the originating AI proposal."""

    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)
    expected_scene_version: int = Field(ge=0)

    @field_validator("title", "content", mode="before")
    @classmethod
    def trim_draft(cls, value):
        return value.strip() if isinstance(value, str) else value


class LegacyManuscriptImportCreate(BaseModel):
    """A human-selected excerpt from a preserved Step 10 legacy draft."""

    scene_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)

    @field_validator("scene_id", "title", "content")
    @classmethod
    def trim_legacy_import(cls, value: str) -> str:
        return value.strip()


class ManuscriptScene(BaseModel):
    id: str
    project_id: str
    scene_id: str
    proposal_id: str
    title: str
    content: str
    version: int = Field(ge=1)
    accepted_at: str


class ManuscriptSceneUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)
    expected_scene_version: int = Field(ge=1, strict=True)

    @field_validator("title", "content")
    @classmethod
    def normalize_scene_update_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class ManuscriptRevision(BaseModel):
    id: str
    project_id: str
    scene_id: str
    proposal_id: str
    title: str
    content: str
    version: int = Field(ge=1)
    created_at: str


class ManuscriptRevisionDiff(BaseModel):
    project_id: str
    left_revision_id: str
    right_revision_id: str
    left_title: str
    right_title: str
    diff_lines: list[str] = Field(default_factory=list)


class ManuscriptExportResponse(BaseModel):
    project_id: str
    title: str
    scene_count: int
    content: str
    generated_at: str


class ManuscriptChapterUpdate(ManuscriptChapterCreate):
    pass


class ManuscriptChapter(ManuscriptChapterCreate):
    id: str
    project_id: str


class ManuscriptProposalCreate(BaseModel):
    scene_id: str = Field(min_length=1, max_length=160)
    source: ManuscriptProposalSource = "scene_contract"
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)
    context: str = Field(default="", max_length=60000)
    checklist: list[str] = Field(default_factory=list)
    generation_review: ManuscriptGenerationReview | None = None

    @field_validator("scene_id", "title", "content", "context")
    @classmethod
    def normalize_proposal_text(cls, value: str) -> str:
        return value.strip()


class ManuscriptProposalStatusUpdate(BaseModel):
    status: ManuscriptProposalStatus


class ManuscriptProposal(ManuscriptProposalCreate):
    id: str
    project_id: str
    status: ManuscriptProposalStatus = "pending_review"
    created_at: str
    reviewed_at: str = ""
