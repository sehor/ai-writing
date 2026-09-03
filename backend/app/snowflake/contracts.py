"""Version 1 structured output contracts for all Snowflake steps."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OneSentenceContract(ContractModel):
    protagonist: str = Field(min_length=1, max_length=200)
    story_goal_or_problem: str = Field(min_length=1, max_length=1000)
    opposition_or_stakes: str = Field(min_length=1, max_length=1000)
    promise: str = Field(min_length=1, max_length=1000)


class DisasterBeat(ContractModel):
    beat_id: str = Field(min_length=1, max_length=80)
    event: str = Field(min_length=1, max_length=2000)
    cause: str = Field(min_length=1, max_length=1000)
    protagonist_action: str = Field(min_length=1, max_length=1000)
    escalation: str = Field(default="", max_length=1000)


class OneParagraphContract(ContractModel):
    setup: DisasterBeat
    disaster_1: DisasterBeat
    disaster_2: DisasterBeat
    disaster_3: DisasterBeat
    ending: DisasterBeat


class CharacterSummary(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    one_sentence_summary: str = Field(min_length=1, max_length=1000)
    motivation: str = Field(min_length=1, max_length=1000)
    goal: str = Field(min_length=1, max_length=1000)
    conflict: str = Field(min_length=1, max_length=1000)
    epiphany: str = Field(min_length=1, max_length=1000)
    viewpoint_summary: str = Field(min_length=1, max_length=4000)


class CharacterSummaryContract(ContractModel):
    characters: list[CharacterSummary] = Field(min_length=1, max_length=100)


class SynopsisParagraph(ContractModel):
    beat_id: Literal["setup", "disaster_1", "disaster_2", "disaster_3", "ending"]
    text: str = Field(min_length=1, max_length=8000)


class OnePageSynopsisContract(ContractModel):
    paragraphs: list[SynopsisParagraph] = Field(min_length=5, max_length=100)


class CharacterViewpoint(ContractModel):
    character_name: str = Field(min_length=1, max_length=120)
    character_ref: str = Field(min_length=1, max_length=160)
    viewpoint_story: str = Field(min_length=1, max_length=12000)
    knows: list[str] = Field(default_factory=list, max_length=200)
    does_not_know: list[str] = Field(default_factory=list, max_length=200)
    misunderstands: list[str] = Field(default_factory=list, max_length=200)


class CharacterViewpointsContract(ContractModel):
    viewpoints: list[CharacterViewpoint] = Field(min_length=1, max_length=100)


class ExpandedSynopsisBlock(ContractModel):
    record_id: str = Field(min_length=1, max_length=160)
    act: str = Field(min_length=1, max_length=120)
    section: str = Field(min_length=1, max_length=120)
    sequence: int = Field(ge=1, le=9999)
    synopsis: str = Field(min_length=1, max_length=40000)
    step4_paragraph_refs: list[str] = Field(default_factory=list, max_length=100)
    character_refs: list[str] = Field(default_factory=list, max_length=100)


class ExpandedSynopsisContract(ContractModel):
    blocks: list[ExpandedSynopsisBlock] = Field(min_length=1, max_length=2000)


class CharacterBibleRecord(ContractModel):
    record_type: Literal["character"]
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    one_sentence_summary: str = Field(min_length=1, max_length=1000)
    motivation: str = Field(min_length=1, max_length=2000)
    goal: str = Field(min_length=1, max_length=2000)
    conflict: str = Field(min_length=1, max_length=2000)
    epiphany: str = Field(min_length=1, max_length=2000)
    viewpoint_summary: str = Field(min_length=1, max_length=12000)
    confirmed_facts: list[str] = Field(default_factory=list, max_length=200)


class WorldBibleRecord(ContractModel):
    record_type: Literal["world", "location", "item", "faction"]
    name: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=12000)
    confirmed_facts: list[str] = Field(default_factory=list, max_length=200)


class StoryThreadActionRecord(ContractModel):
    action: Literal[
        "plant", "reinforce", "misdirect", "escalate", "partial_payoff", "payoff"
    ]
    thread_title: str = Field(min_length=1, max_length=160)


class SceneListRecord(ContractModel):
    title: str = Field(min_length=1, max_length=160)
    pov: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=1000)
    conflict: str = Field(min_length=1, max_length=1000)
    turning_point: str = Field(min_length=1, max_length=1000)
    outcome: str = Field(min_length=1, max_length=1000)
    required_canon_ids: list[str] = Field(default_factory=list, max_length=200)
    forbidden_facts: list[str] = Field(default_factory=list, max_length=200)
    information_delta: str = Field(min_length=1, max_length=4000)
    character_state_delta: str = Field(min_length=1, max_length=4000)
    story_thread_actions: list[StoryThreadActionRecord] = Field(
        default_factory=list, max_length=100
    )


class SceneExpansionRecord(ContractModel):
    scene_id: str = Field(min_length=1, max_length=160)
    beats: list[str] = Field(min_length=1, max_length=200)
    emotional_change: str = Field(min_length=1, max_length=4000)
    chapter_plan: str = Field(min_length=1, max_length=4000)


STEP_CONTRACTS = {
    1: OneSentenceContract,
    2: OneParagraphContract,
    3: CharacterSummaryContract,
    4: OnePageSynopsisContract,
    5: CharacterViewpointsContract,
    6: ExpandedSynopsisContract,
}


RECORD_CONTRACTS = {
    6: ExpandedSynopsisBlock,
    8: SceneListRecord,
    9: SceneExpansionRecord,
}


RECORD_STEP_NUMBERS = frozenset({6, 7, 8, 9})
