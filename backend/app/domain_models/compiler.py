from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain_models.manuscript import ManuscriptProposalStatus
from app.domain_models.scene import SceneContract
from app.domain_models.writeback import WritebackProposal

SceneProposalStatus = ManuscriptProposalStatus


class SceneProposalCreate(BaseModel):
    operation: Literal["create", "update"] = "create"
    source_record_id: str = ""
    source_record_revision_id: str = ""
    target_scene_id: str = ""
    expected_plan_version: int = Field(default=0, ge=0)
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """A parsed Step 8 scene awaiting batch review."""

    sequence: int = Field(ge=1, le=999)
    chapter_id: str = Field(default="", max_length=160)
    chapter_hint: str = Field(default="", max_length=160)
    title: str = Field(min_length=1, max_length=160)
    pov: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=1000)
    conflict: str = Field(default="", max_length=1000)
    turning_point: str = Field(default="", max_length=1000)
    outcome: str = Field(default="", max_length=1000)
    required_canon_ids: str = Field(default="", max_length=2000)
    required_canon_raw: str = Field(default="", max_length=4000)
    forbidden_fact_refs: str = Field(default="", max_length=4000)
    information_delta: str = Field(default="", max_length=4000)
    character_state_delta: str = Field(default="", max_length=4000)
    story_thread_actions: str = Field(default="", max_length=4000)
    open_threads: str = Field(
        default="",
        max_length=4000,
        json_schema_extra={"deprecated": True},
        description=(
            "Legacy compatibility notes retained during import. Structured StoryThread actions "
            "are the generation source."
        ),
    )
    source_ref: str = Field(default="", max_length=160)
    source_excerpt: str = Field(default="", max_length=2000)
    warnings: list[str] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)

    @field_validator(
        "chapter_id",
        "chapter_hint",
        "title",
        "pov",
        "goal",
        "conflict",
        "turning_point",
        "outcome",
        "required_canon_ids",
        "required_canon_raw",
        "forbidden_fact_refs",
        "information_delta",
        "character_state_delta",
        "story_thread_actions",
        "open_threads",
        "source_ref",
    )
    @classmethod
    def normalize_scene_proposal_text(cls, value: str) -> str:
        return value.strip()


class SceneProposalAcceptRequest(BaseModel):
    """Empty proposal_ids accepts every pending proposal for the project."""

    proposal_ids: list[str] = Field(default_factory=list)


class CompileRunInfo(BaseModel):
    run_id: str
    run_version: int
    cached: bool


class CanonExtractionReport(BaseModel):
    """Step 7 artifact compiled into Canon create / update proposals."""

    project_id: str
    step_number: int
    processor: str
    cached: bool
    run_id: str
    run_version: int
    warnings: list[str] = Field(default_factory=list)
    proposals: list[WritebackProposal] = Field(default_factory=list)


class SceneProposal(SceneProposalCreate):
    id: str
    project_id: str
    status: SceneProposalStatus = "pending_review"
    applied_scene_id: str = ""
    created_at: str
    reviewed_at: str = ""


class SceneProposalStatusUpdate(BaseModel):
    status: SceneProposalStatus


class SceneParseReport(BaseModel):
    """Step 8 artifact parsed into reviewable Scene Contract proposals."""

    project_id: str
    step_number: int
    processor: str
    cached: bool
    run_id: str
    run_version: int
    warnings: list[str] = Field(default_factory=list)
    proposals: list[SceneProposal] = Field(default_factory=list)
    thread_proposals: list[WritebackProposal] = Field(default_factory=list)


class SceneProposalAcceptanceReport(BaseModel):
    project_id: str
    scenes: list[SceneContract] = Field(default_factory=list)
    proposals: list[SceneProposal] = Field(default_factory=list)
