from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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


class ReferenceGenerationRequest(ModelExecutionOptions):
    suggestion_type: ReferenceSuggestionType = "brainstorm"
    scope_type: ReferenceScopeType = "project"
    scope_ref: str = Field(default="", max_length=160)
    author_problem: str = Field(min_length=1, max_length=4000)
    desired_output: str = Field(default="", max_length=1000)

    @field_validator("scope_ref", "author_problem", "desired_output")
    @classmethod
    def normalize_reference_request_text(cls, value: str) -> str:
        return value.strip()


class ReferenceSuggestionCreate(BaseModel):
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
