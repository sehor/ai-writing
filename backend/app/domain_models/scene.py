from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SceneContractCreate(BaseModel):
    chapter_id: str = Field(default="", max_length=160)
    sequence: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=160)
    pov: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=1000)
    conflict: str = Field(default="", max_length=1000)
    turning_point: str = Field(default="", max_length=1000)
    outcome: str = Field(default="", max_length=1000)
    required_canon: str = Field(default="", max_length=4000)
    forbidden_facts: str = Field(default="", max_length=4000)
    information_delta: str = Field(default="", max_length=4000)
    character_state_delta: str = Field(default="", max_length=4000)
    story_thread_actions: str = Field(default="", max_length=4000)
    open_threads: str = Field(
        default="",
        max_length=4000,
        json_schema_extra={"deprecated": True},
        description=(
            "Legacy compatibility notes. Excluded from generation context; use structured "
            "StoryThread records and events."
        ),
    )
    source_artifact_step: int = Field(default=8, ge=1, le=10)

    @field_validator(
        "chapter_id",
        "title",
        "pov",
        "goal",
        "conflict",
        "turning_point",
        "outcome",
        "required_canon",
        "forbidden_facts",
        "information_delta",
        "character_state_delta",
        "story_thread_actions",
        "open_threads",
    )
    @classmethod
    def normalize_scene_text(cls, value: str) -> str:
        return value.strip()


class SceneContractUpdate(SceneContractCreate):
    pass


class SceneContract(SceneContractCreate):
    id: str
    project_id: str
    plan_version: int = Field(default=1, ge=1)
    source_record_step: Literal[0, 8] = 0
    source_record_id: str = ""
    source_record_revision_id: str = ""
    manuscript_plan_version: int = Field(default=0, ge=0)
