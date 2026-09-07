from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MemoryRecordType = Literal[
    "chapter_summary",
    "prose_sample",
    "voice_sample",
    "style_rule",
]


class MemoryRecordCreate(BaseModel):
    record_type: MemoryRecordType
    title: str = Field(min_length=1, max_length=160)
    scope: str = Field(default="", max_length=160)
    content: str = Field(min_length=1, max_length=12000)
    tags: str = Field(default="", max_length=1000)
    source_ref: str = Field(default="", max_length=160)

    @field_validator("title", "scope", "content", "tags", "source_ref")
    @classmethod
    def normalize_memory_text(cls, value: str) -> str:
        return value.strip()


class MemoryRecordUpdate(MemoryRecordCreate):
    pass


class MemoryRecord(MemoryRecordCreate):
    id: str
    project_id: str
