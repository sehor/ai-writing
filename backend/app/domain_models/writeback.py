from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

WritebackTarget = Literal[
    "canon_entity",
    "memory_record",
    "narrative_relation",
    "story_thread",
    "story_thread_event",
    "story_thread_status",
]


WritebackAction = Literal["create", "update"]


WritebackProposalStatus = Literal["pending_review", "accepted", "rejected", "superseded"]


class WritebackProposalCreate(BaseModel):
    target: WritebackTarget
    action: WritebackAction = "create"
    title: str = Field(min_length=1, max_length=160)
    rationale: str = Field(default="", max_length=4000)
    payload: dict = Field(default_factory=dict)
    source_ref: str = Field(default="", max_length=160)
    # Update proposals carry an optimistic-concurrency handle on the
    # existing record plus field-level before/after changes.
    target_record_id: str = Field(default="", max_length=160)
    expected_version: int | None = Field(default=None, ge=1)
    changes: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("title", "rationale", "source_ref", "target_record_id")
    @classmethod
    def normalize_writeback_text(cls, value: str) -> str:
        return value.strip()


class WritebackProposalStatusUpdate(BaseModel):
    status: WritebackProposalStatus


class WritebackProposal(WritebackProposalCreate):
    id: str
    project_id: str
    status: WritebackProposalStatus = "pending_review"
    created_at: str
    reviewed_at: str = ""
    applied_record_id: str = ""
