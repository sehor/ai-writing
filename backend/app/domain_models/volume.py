"""Optional manuscript organization; scene sequence remains the narrative clock."""

from pydantic import BaseModel, Field, field_validator


class ManuscriptVolumeCreate(BaseModel):
    sequence: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=160)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ManuscriptVolume(ManuscriptVolumeCreate):
    id: str
    project_id: str
    chapter_ids: list[str] = Field(default_factory=list)


class ChapterVolumeAssignment(BaseModel):
    volume_id: str = Field(default="", max_length=160)


class ChapterVolumeMembership(ChapterVolumeAssignment):
    chapter_id: str
