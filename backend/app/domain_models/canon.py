from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CanonEntityType = Literal["character", "location", "item", "faction", "rule"]


class CanonEntityCreate(BaseModel):
    entity_type: CanonEntityType
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=1000)
    current_state: str = Field(default="", max_length=4000)
    constraints: str = Field(default="", max_length=4000)
    last_seen: str = Field(default="", max_length=120)
    timeline_notes: str = Field(default="", max_length=8000)

    @field_validator(
        "name",
        "summary",
        "current_state",
        "constraints",
        "last_seen",
        "timeline_notes",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class CanonEntityUpdate(CanonEntityCreate):
    pass


class CanonEntity(CanonEntityCreate):
    id: str
    project_id: str
    version: int = Field(default=1, ge=1)
    updated_at: str = ""
