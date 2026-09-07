from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain_models.model import ModelExecutionOptions, WorkflowAgentTrace
from app.domain_models.writeback import WritebackProposalCreate

ReferenceScopeType = Literal[
    "project",
    "snowflake_step",
    "scene",
    "canon_entity",
    "memory_record",
    "manuscript_scene",
    "graph",
]


ReferenceSuggestionType = Literal[
    "brainstorm",
    "scene_bridge",
    "conflict_options",
    "character_motivation",
    "canon_gap",
    "prose_reference",
    "structure_fix",
]


ReferenceSuggestionStatus = Literal["pending_review", "accepted", "rejected", "superseded"]


class ReferenceEditorContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=160)
    scene_id: str = Field(min_length=1, max_length=160)
    source_kind: Literal["accepted_manuscript", "proposal_draft"]
    proposal_id: str = Field(default="", max_length=160)
    expected_scene_version: int = Field(ge=0, strict=True)
    session_id: str = Field(min_length=1, max_length=160)
    snapshot_text: str = Field(min_length=1, max_length=40000)
    selection_mode: Literal["selection", "whole_scene"]
    selection_start: int = Field(ge=0, strict=True)
    selection_end: int = Field(ge=0, strict=True)
    selected_text: str = Field(min_length=1, max_length=40000)

    @model_validator(mode="after")
    def validate_selection(self):
        if bool(self.proposal_id) != (self.source_kind == "proposal_draft"):
            raise ValueError("Only a proposal draft requires a proposal ID.")
        raw = self.snapshot_text.encode("utf-16-le")
        if not 0 <= self.selection_start < self.selection_end <= len(raw) // 2:
            raise ValueError("Selection is outside the draft.")
        try:
            selected = raw[self.selection_start * 2 : self.selection_end * 2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError("Selection splits a Unicode character.") from exc
        if selected != self.selected_text or not selected.strip():
            raise ValueError("Selection does not match the draft.")
        if self.selection_mode == "whole_scene" and (
            self.selection_start != 0 or self.selection_end != len(raw) // 2
        ):
            raise ValueError("Whole-scene selection must include the complete draft.")
        return self


class ReferenceGenerationRequest(ModelExecutionOptions):
    suggestion_type: ReferenceSuggestionType = "brainstorm"
    scope_type: ReferenceScopeType = "project"
    scope_ref: str = Field(default="", max_length=160)
    author_problem: str = Field(min_length=1, max_length=4000)
    desired_output: str = Field(default="", max_length=1000)
    editor_context: ReferenceEditorContext | None = None

    @field_validator("scope_ref", "author_problem", "desired_output")
    @classmethod
    def normalize_reference_request_text(cls, value: str) -> str:
        return value.strip()


class ReferenceSuggestionCreate(BaseModel):
    editor_context: ReferenceEditorContext | None = None
    suggestion_type: ReferenceSuggestionType
    scope_type: ReferenceScopeType
    scope_ref: str = Field(default="", max_length=160)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)
    rationale: str = Field(default="", max_length=4000)
    used_context: str = Field(default="", max_length=60000)
    canon_warnings: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    graph_warnings: list[str] = Field(default_factory=list)
    proposed_writebacks: list[WritebackProposalCreate] = Field(default_factory=list)
    workflow_trace: list[WorkflowAgentTrace] = Field(default_factory=list)

    @field_validator("scope_ref", "title", "content", "rationale", "used_context")
    @classmethod
    def normalize_reference_suggestion_text(cls, value: str) -> str:
        return value.strip()


class ReferenceSuggestionStatusUpdate(BaseModel):
    status: ReferenceSuggestionStatus


class ReferenceSuggestion(ReferenceSuggestionCreate):
    id: str
    project_id: str
    status: ReferenceSuggestionStatus = "pending_review"
    created_at: str
    reviewed_at: str = ""

    @model_validator(mode="after")
    def validate_editor_source(self):
        if self.editor_context and (
            self.editor_context.project_id != self.project_id
            or self.scope_type != "scene"
            or self.scope_ref != self.editor_context.scene_id
        ):
            raise ValueError("Reference editor source belongs to another project or scene.")
        return self
