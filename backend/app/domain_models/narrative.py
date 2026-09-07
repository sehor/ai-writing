from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

StoryFactStatus = Literal["planned", "confirmed", "superseded", "retracted"]


KnowledgeScope = Literal["world_truth", "reader_knowledge", "character_knowledge"]


NarrativeRelationStatus = Literal["planned", "confirmed", "superseded"]


StoryThreadType = Literal["foreshadow", "mystery", "relationship", "conflict", "promise", "subplot"]


StoryThreadStatus = Literal["planned", "planted", "developing", "dormant", "paid_off", "abandoned"]


StoryThreadAction = Literal[
    "plant", "reinforce", "misdirect", "escalate", "partial_payoff", "payoff"
]


class CharacterKnowledgeCreate(BaseModel):
    character: str = Field(min_length=1, max_length=160)
    known_from_scene: int = Field(ge=0, le=999)

    @field_validator("character")
    @classmethod
    def normalize_character_name(cls, value: str) -> str:
        return value.strip()


class NarrativeChangeReason(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class StoryFactCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    predicate: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=4000)
    valid_from_scene: int = Field(ge=0, le=999)
    valid_to_scene: int | None = Field(default=None, ge=0, le=999)
    reader_visible_from: int | None = Field(default=None, ge=0, le=999)
    source_ref: str = Field(default="", max_length=240)
    status: StoryFactStatus = "confirmed"

    @field_validator("subject", "predicate", "value", "source_ref")
    @classmethod
    def normalize_story_fact_text(cls, value: str) -> str:
        return value.strip()


class KnowledgeStateCreate(BaseModel):
    scope: KnowledgeScope
    character: str = Field(default="", max_length=160)
    known_from_scene: int = Field(ge=0, le=999)
    source_ref: str = Field(default="", max_length=240)
    status: StoryFactStatus = "confirmed"

    @field_validator("character", "source_ref")
    @classmethod
    def normalize_knowledge_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_scope_subject(self) -> "KnowledgeStateCreate":
        if self.scope == "character_knowledge" and not self.character:
            raise ValueError("character is required for character_knowledge")
        if self.scope != "character_knowledge" and self.character:
            raise ValueError("character is only valid for character_knowledge")
        return self


class CharacterKnowledge(CharacterKnowledgeCreate):
    fact_id: str
    project_id: str


class NarrativeVersionChange(NarrativeChangeReason):
    expected_version: int = Field(ge=1)


class NarrativeRelationCreate(BaseModel):
    source: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=240)
    relation: str = Field(min_length=1, max_length=160)
    valid_from: int = Field(ge=0, le=999)
    valid_to: int | None = Field(default=None, ge=0, le=999)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_ref: str = Field(default="", max_length=240)
    status: NarrativeRelationStatus = "confirmed"

    @field_validator("source", "target", "relation", "source_ref")
    @classmethod
    def normalize_narrative_relation_text(cls, value: str) -> str:
        return value.strip()


class StoryThreadCreate(BaseModel):
    thread_type: StoryThreadType
    title: str = Field(min_length=1, max_length=240)
    status: StoryThreadStatus = "planned"
    planted_at: int | None = Field(default=None, ge=0, le=999)
    target_payoff_from: int | None = Field(default=None, ge=0, le=999)
    target_payoff_to: int | None = Field(default=None, ge=0, le=999)
    importance: int = Field(default=3, ge=1, le=5)
    reveal_constraints: str = Field(default="", max_length=4000)

    @field_validator("title", "reveal_constraints")
    @classmethod
    def normalize_story_thread_text(cls, value: str) -> str:
        return value.strip()


class StoryThreadStatusUpdate(BaseModel):
    status: StoryThreadStatus


class StoryThreadEventCreate(BaseModel):
    scene_id: str = Field(min_length=1, max_length=160)
    action: StoryThreadAction
    note: str = Field(default="", max_length=2000)

    @field_validator("scene_id", "note")
    @classmethod
    def normalize_story_thread_event_text(cls, value: str) -> str:
        return value.strip()


class StoryFact(StoryFactCreate):
    id: str
    project_id: str
    version: int = Field(default=1, ge=1)
    updated_at: str = ""


class KnowledgeState(KnowledgeStateCreate):
    id: str
    fact_id: str
    project_id: str
    version: int = Field(default=1, ge=1)
    updated_at: str = ""


class StoryFactCorrection(StoryFactCreate, NarrativeVersionChange):
    pass


class KnowledgeStateAuthorCreate(KnowledgeStateCreate, NarrativeChangeReason):
    pass


class KnowledgeStateCorrection(KnowledgeStateCreate, NarrativeVersionChange):
    pass


class NarrativeRelation(NarrativeRelationCreate):
    id: str
    project_id: str


class StoryThread(StoryThreadCreate):
    id: str
    project_id: str


class StoryThreadEvent(StoryThreadEventCreate):
    id: str
    project_id: str
    thread_id: str


class NarrativeRevision(BaseModel):
    id: str
    project_id: str
    fact_id: str
    knowledge_state_id: str = ""
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    created_at: str
    record: StoryFact | KnowledgeState

    @model_validator(mode="after")
    def validate_identity(self) -> "NarrativeRevision":
        record = self.record
        if record.project_id != self.project_id or record.version != self.version:
            raise ValueError("Narrative history identity/version mismatch")
        if self.knowledge_state_id:
            if not isinstance(record, KnowledgeState) or (
                record.id != self.knowledge_state_id or record.fact_id != self.fact_id
            ):
                raise ValueError("Narrative knowledge history target mismatch")
        elif not isinstance(record, StoryFact) or record.id != self.fact_id:
            raise ValueError("Narrative fact history target mismatch")
        return self


class StoryStateResponse(BaseModel):
    project_id: str
    scene_position: int
    character: str = ""
    world_truth: list[StoryFact] = Field(default_factory=list)
    reader_knowledge: list[StoryFact] = Field(default_factory=list)
    character_knowledge: list[StoryFact] = Field(default_factory=list)
