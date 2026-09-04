"""Version 2 Snowflake output contracts with version 1 input compatibility."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OneSentenceContract(ContractModel):
    one_sentence_summary: str = Field(min_length=1, max_length=2000)
    protagonist_descriptor: str = Field(min_length=1, max_length=200)
    central_story_problem: str = Field(min_length=1, max_length=1000)
    stakes: str | None = Field(default=None, max_length=1000)
    language: str = Field(min_length=1, max_length=80)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "one_sentence_summary" in value:
            return value
        if "protagonist" not in value:
            return value
        return {
            "one_sentence_summary": value.get("promise") or value.get("story_goal_or_problem"),
            "protagonist_descriptor": value.get("protagonist"),
            "central_story_problem": value.get("story_goal_or_problem"),
            "stakes": value.get("opposition_or_stakes") or None,
            "language": "undetermined",
            "source_refs": [],
        }


class DisasterDetail(ContractModel):
    sentence: str = Field(min_length=1, max_length=2000)
    trigger: str = Field(min_length=1, max_length=1000)
    protagonist_choice_or_action: str | None = Field(default=None, max_length=1000)
    irreversible_change: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "sentence" in value:
            return value
        if "event" not in value:
            return value
        return {
            "sentence": value.get("event"),
            "trigger": value.get("cause") or "TBD",
            "protagonist_choice_or_action": value.get("protagonist_action") or None,
            "irreversible_change": value.get("escalation") or value.get("event"),
        }


class EndingDetail(ContractModel):
    sentence: str = Field(min_length=1, max_length=2000)
    climax_and_resolution: str = Field(min_length=1, max_length=2000)
    external_outcome: str = Field(min_length=1, max_length=2000)
    internal_change: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "sentence" in value:
            return value
        if "event" not in value:
            return value
        event = value.get("event")
        return {
            "sentence": event,
            "climax_and_resolution": event,
            "external_outcome": value.get("escalation") or event,
            "internal_change": None,
        }


class OneParagraphContract(ContractModel):
    setup: str = Field(min_length=1, max_length=2000)
    disaster_1: DisasterDetail
    disaster_2: DisasterDetail
    disaster_3: DisasterDetail
    ending: EndingDetail
    rendered_paragraph: str = Field(min_length=1, max_length=12000)
    causal_links: list[str] = Field(default_factory=list, max_length=200)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "rendered_paragraph" in value:
            return value
        setup = value.get("setup")
        if not isinstance(setup, dict):
            return value
        events = [
            item.get("event", "") if isinstance(item, dict) else ""
            for item in (
                setup,
                value.get("disaster_1"),
                value.get("disaster_2"),
                value.get("disaster_3"),
                value.get("ending"),
            )
        ]
        migrated = dict(value)
        migrated["setup"] = setup.get("event") or "TBD"
        migrated["rendered_paragraph"] = " ".join(item for item in events if item)
        migrated["causal_links"] = []
        migrated["source_refs"] = []
        return migrated


class CharacterSummary(ContractModel):
    character_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    story_role: str = Field(min_length=1, max_length=120)
    one_sentence_storyline: str = Field(min_length=1, max_length=1000)
    motivation: str = Field(min_length=1, max_length=1000)
    goal: str = Field(min_length=1, max_length=1000)
    goal_success_test: str = Field(min_length=1, max_length=1000)
    conflict: str = Field(min_length=1, max_length=1000)
    epiphany_or_change: str = Field(min_length=1, max_length=1000)
    one_paragraph_storyline: str = Field(min_length=1, max_length=6000)
    relationship_to_main_plot: str = Field(min_length=1, max_length=2000)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "character_id" in value:
            return value
        if "name" not in value:
            return value
        name = str(value.get("name"))
        return {
            "character_id": name.lower().replace(" ", "-"),
            "name": name,
            "story_role": value.get("role") or "TBD",
            "one_sentence_storyline": value.get("one_sentence_summary") or "TBD",
            "motivation": value.get("motivation") or "TBD",
            "goal": value.get("goal") or "TBD",
            "goal_success_test": value.get("goal") or "TBD",
            "conflict": value.get("conflict") or "TBD",
            "epiphany_or_change": value.get("epiphany") or "TBD",
            "one_paragraph_storyline": value.get("viewpoint_summary") or "TBD",
            "relationship_to_main_plot": value.get("role") or "TBD",
            "source_refs": [],
        }


class CharacterCoverage(ContractModel):
    main_characters_included: list[str] = Field(default_factory=list, max_length=200)
    missing_or_uncertain_characters: list[str] = Field(default_factory=list, max_length=200)


class CharacterSummaryContract(ContractModel):
    characters: list[CharacterSummary] = Field(min_length=1, max_length=100)
    coverage: CharacterCoverage = Field(default_factory=CharacterCoverage)


class SynopsisParagraph(ContractModel):
    paragraph_id: str = Field(min_length=1, max_length=20)
    source_beat: Literal["setup", "disaster_1", "disaster_2", "disaster_3", "ending"]
    text: str = Field(min_length=1, max_length=8000)
    ending_turn_or_worsening: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "source_beat" in value:
            return value
        beat_id = value.get("beat_id")
        if beat_id is None:
            return value
        order = {
            "setup": "P1",
            "disaster_1": "P2",
            "disaster_2": "P3",
            "disaster_3": "P4",
            "ending": "P5",
        }
        return {
            "paragraph_id": order.get(str(beat_id), str(beat_id)),
            "source_beat": beat_id,
            "text": value.get("text"),
            "ending_turn_or_worsening": None,
        }


class MajorDisasterAnchor(ContractModel):
    disaster: Literal["disaster_1", "disaster_2", "disaster_3"]
    paragraph_ids: list[str] = Field(min_length=1, max_length=20)


class OnePageSynopsisContract(ContractModel):
    paragraphs: list[SynopsisParagraph] = Field(min_length=5, max_length=5)
    rendered_synopsis: str = Field(min_length=1, max_length=50000)
    major_disaster_anchors: list[MajorDisasterAnchor] = Field(min_length=3, max_length=3)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "rendered_synopsis" in value:
            return value
        paragraphs = value.get("paragraphs")
        if not isinstance(paragraphs, list):
            return value
        return {
            "paragraphs": paragraphs,
            "rendered_synopsis": "\n\n".join(
                str(item.get("text", "")) for item in paragraphs if isinstance(item, dict)
            ),
            "major_disaster_anchors": [
                {"disaster": beat, "paragraph_ids": [f"P{index}"]}
                for index, beat in enumerate(
                    ("disaster_1", "disaster_2", "disaster_3"), start=2
                )
            ],
            "source_refs": [],
        }


class CharacterDecision(ContractModel):
    decision: str = Field(min_length=1, max_length=2000)
    reason_from_character_view: str = Field(min_length=1, max_length=2000)
    consequence: str = Field(min_length=1, max_length=2000)


class CharacterSynopsis(ContractModel):
    character_id: str = Field(min_length=1, max_length=160)
    importance: Literal["major", "supporting_important"]
    subjective_synopsis: str = Field(min_length=1, max_length=20000)
    initial_want_and_belief: str = Field(min_length=1, max_length=4000)
    known_facts: list[str] = Field(default_factory=list, max_length=200)
    unknown_facts: list[str] = Field(default_factory=list, max_length=200)
    misbeliefs: list[str] = Field(default_factory=list, max_length=200)
    key_decisions: list[CharacterDecision] = Field(default_factory=list, max_length=200)
    relationship_changes: list[str] = Field(default_factory=list, max_length=200)
    ending_view_and_change: str = Field(min_length=1, max_length=4000)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "subjective_synopsis" in value:
            return value
        if "viewpoint_story" not in value:
            return value
        return {
            "character_id": value.get("character_ref") or value.get("character_name"),
            "importance": "major",
            "subjective_synopsis": value.get("viewpoint_story"),
            "initial_want_and_belief": "TBD",
            "known_facts": value.get("knows", []),
            "unknown_facts": value.get("does_not_know", []),
            "misbeliefs": value.get("misunderstands", []),
            "key_decisions": [],
            "relationship_changes": [],
            "ending_view_and_change": "TBD",
            "source_refs": [],
        }


class CharacterView(ContractModel):
    character_id: str = Field(min_length=1, max_length=160)
    view: str = Field(min_length=1, max_length=4000)


class CrossViewConflict(ContractModel):
    topic: str = Field(min_length=1, max_length=1000)
    character_views: list[CharacterView] = Field(min_length=2, max_length=100)


class CharacterViewpointsContract(ContractModel):
    character_synopses: list[CharacterSynopsis] = Field(min_length=1, max_length=100)
    cross_view_conflicts: list[CrossViewConflict] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "character_synopses" in value:
            return value
        if "viewpoints" not in value:
            return value
        return {"character_synopses": value.get("viewpoints"), "cross_view_conflicts": []}


class ExpandedSynopsisBlock(ContractModel):
    section_id: str = Field(min_length=1, max_length=160)
    source_paragraph_ids: list[str] = Field(default_factory=list, max_length=100)
    story_phase: str = Field(min_length=1, max_length=120)
    synopsis: str = Field(min_length=1, max_length=40000)
    character_strategies_and_decisions: list[str] = Field(default_factory=list, max_length=200)
    causal_entry_state: str = Field(min_length=1, max_length=4000)
    causal_exit_state: str = Field(min_length=1, max_length=4000)
    subplot_actions: list[str] = Field(default_factory=list, max_length=200)
    setups: list[str] = Field(default_factory=list, max_length=200)
    payoffs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "section_id" in value:
            return value
        if "record_id" not in value:
            return value
        synopsis = value.get("synopsis") or "TBD"
        return {
            "section_id": value.get("record_id"),
            "source_paragraph_ids": value.get("step4_paragraph_refs", []),
            "story_phase": value.get("section") or value.get("act") or "TBD",
            "synopsis": synopsis,
            "character_strategies_and_decisions": value.get("character_refs", []),
            "causal_entry_state": "TBD",
            "causal_exit_state": synopsis,
            "subplot_actions": [],
            "setups": [],
            "payoffs": [],
        }


class CausalLink(ContractModel):
    cause: str = Field(min_length=1, max_length=4000)
    effect: str = Field(min_length=1, max_length=4000)
    source_refs: list[str] = Field(default_factory=list, max_length=200)


class SubplotLedgerEntry(ContractModel):
    subplot_id: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=2000)
    entry: str = Field(min_length=1, max_length=2000)
    turns: list[str] = Field(default_factory=list, max_length=200)
    resolution: str = Field(min_length=1, max_length=2000)


class ExpandedSynopsisContract(ContractModel):
    sections: list[ExpandedSynopsisBlock] = Field(min_length=1, max_length=2000)
    rendered_long_synopsis: str = Field(min_length=1, max_length=200000)
    causal_chain: list[CausalLink] = Field(default_factory=list, max_length=2000)
    subplot_ledger: list[SubplotLedgerEntry] = Field(default_factory=list, max_length=500)
    open_logic_questions: list[str] = Field(default_factory=list, max_length=500)
    source_refs: list[str] = Field(default_factory=list, max_length=500)


class CharacterIdentity(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    age_or_life_stage: str | None = Field(default=None, max_length=200)
    role: str = Field(min_length=1, max_length=120)
    appearance: str | None = Field(default=None, max_length=4000)


class CharacterConflicts(ContractModel):
    external: list[str] = Field(default_factory=list, max_length=200)
    internal: list[str] = Field(default_factory=list, max_length=200)
    relational: list[str] = Field(default_factory=list, max_length=200)


class CharacterTraits(ContractModel):
    fears: list[str] = Field(default_factory=list, max_length=100)
    needs: list[str] = Field(default_factory=list, max_length=100)
    strengths: list[str] = Field(default_factory=list, max_length=100)
    flaws: list[str] = Field(default_factory=list, max_length=100)


class CharacterRelationship(ContractModel):
    other_character_id: str = Field(min_length=1, max_length=160)
    start_state: str = Field(min_length=1, max_length=2000)
    pressure: str = Field(min_length=1, max_length=2000)
    end_state: str = Field(min_length=1, max_length=2000)


class VoiceAndBehavior(ContractModel):
    speech_tendencies: list[str] = Field(default_factory=list, max_length=100)
    habits_or_tells: list[str] = Field(default_factory=list, max_length=100)
    decision_pattern: str = Field(min_length=1, max_length=2000)
    behavior_under_pressure: str = Field(min_length=1, max_length=2000)


class CharacterArc(ContractModel):
    start_state: str = Field(min_length=1, max_length=2000)
    inciting_pressure: str = Field(min_length=1, max_length=2000)
    turning_points: list[str] = Field(default_factory=list, max_length=100)
    epiphany_or_refusal: str = Field(min_length=1, max_length=2000)
    end_state: str = Field(min_length=1, max_length=2000)
    change_statement: str = Field(min_length=1, max_length=2000)


class CanonFactCandidate(ContractModel):
    claim: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=2000)
    status: Literal["proposal"] = "proposal"


class CharacterBibleRecord(ContractModel):
    character_id: str = Field(min_length=1, max_length=160)
    identity: CharacterIdentity
    formative_history: list[str] = Field(default_factory=list, max_length=200)
    motivation: str = Field(min_length=1, max_length=2000)
    story_goal: str = Field(min_length=1, max_length=2000)
    goal_success_test: str = Field(min_length=1, max_length=2000)
    conflicts: CharacterConflicts
    beliefs_and_misbeliefs: list[str] = Field(default_factory=list, max_length=200)
    fears_needs_strengths_flaws: CharacterTraits
    relationships: list[CharacterRelationship] = Field(default_factory=list, max_length=200)
    voice_and_behavior: VoiceAndBehavior
    arc: CharacterArc
    plot_function: str = Field(min_length=1, max_length=2000)
    continuity_constraints: list[str] = Field(default_factory=list, max_length=200)
    canon_fact_candidates: list[CanonFactCandidate] = Field(default_factory=list, max_length=200)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "identity" in value:
            return value
        if value.get("record_type") != "character":
            return value
        name = value.get("name") or "TBD"
        role = value.get("role") or "TBD"
        conflict = value.get("conflict") or "TBD"
        epiphany = value.get("epiphany") or "TBD"
        return {
            "character_id": str(name).lower().replace(" ", "-"),
            "identity": {"name": name, "aliases": [], "role": role},
            "formative_history": [],
            "motivation": value.get("motivation") or "TBD",
            "story_goal": value.get("goal") or "TBD",
            "goal_success_test": value.get("goal") or "TBD",
            "conflicts": {"external": [conflict], "internal": [], "relational": []},
            "beliefs_and_misbeliefs": [],
            "fears_needs_strengths_flaws": {
                "fears": [], "needs": [], "strengths": [], "flaws": []
            },
            "relationships": [],
            "voice_and_behavior": {
                "speech_tendencies": [],
                "habits_or_tells": [],
                "decision_pattern": "TBD",
                "behavior_under_pressure": "TBD",
            },
            "arc": {
                "start_state": value.get("viewpoint_summary") or "TBD",
                "inciting_pressure": conflict,
                "turning_points": [],
                "epiphany_or_refusal": epiphany,
                "end_state": epiphany,
                "change_statement": epiphany,
            },
            "plot_function": role,
            "continuity_constraints": value.get("confirmed_facts", []),
            "canon_fact_candidates": [
                {
                    "claim": fact,
                    "reason": "Migrated from a version 1 confirmed_facts entry for human review.",
                    "status": "proposal",
                }
                for fact in value.get("confirmed_facts", [])
                if str(fact).strip()
            ],
            "source_refs": [],
        }


class WorldBibleRecord(ContractModel):
    """Legacy Step 7 record retained for reading existing projects only."""

    record_type: Literal["world", "location", "item", "faction"]
    name: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=12000)
    confirmed_facts: list[str] = Field(default_factory=list, max_length=200)


class StoryThreadActionRecord(ContractModel):
    thread_id: str = Field(min_length=1, max_length=160)
    action: Literal["open", "advance", "complicate", "payoff", "close"]
    description: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "thread_id" in value:
            return value
        action_map = {
            "plant": "open",
            "reinforce": "advance",
            "misdirect": "complicate",
            "escalate": "complicate",
            "partial_payoff": "payoff",
            "payoff": "payoff",
        }
        title = value.get("thread_title") or "TBD"
        return {
            "thread_id": str(title).lower().replace(" ", "-"),
            "action": action_map.get(value.get("action"), "advance"),
            "description": title,
        }


class SceneListRecord(ContractModel):
    scene_id: str = Field(min_length=1, max_length=160)
    sequence: int = Field(ge=1, le=999999)
    chapter_hint: str | None = Field(default=None, max_length=160)
    pov_character_id: str = Field(min_length=1, max_length=160)
    time_and_location: str | None = Field(default=None, max_length=1000)
    what_happens: str = Field(min_length=1, max_length=4000)
    goal: str = Field(min_length=1, max_length=1000)
    conflict: str = Field(min_length=1, max_length=1000)
    turning_point: str = Field(min_length=1, max_length=1000)
    outcome: Literal["success", "failure", "mixed", "disaster"]
    exit_condition: str = Field(min_length=1, max_length=2000)
    information_delta: list[str] = Field(default_factory=list, max_length=200)
    character_state_delta: list[str] = Field(default_factory=list, max_length=200)
    required_canon_refs: list[str] = Field(default_factory=list, max_length=200)
    forbidden_fact_refs: list[str] = Field(default_factory=list, max_length=200)
    story_thread_actions: list[StoryThreadActionRecord] = Field(default_factory=list, max_length=100)
    estimated_words: int | None = Field(default=None, ge=1, le=100000)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "pov_character_id" in value:
            return value
        if "pov" not in value:
            return value
        raw_outcome = str(value.get("outcome") or "")
        lowered = raw_outcome.lower()
        outcome = next(
            (item for item in ("success", "failure", "mixed", "disaster") if item in lowered),
            "mixed",
        )
        scene_id = value.get("scene_id") or value.get("title") or "scene"
        return {
            "scene_id": str(scene_id).lower().replace(" ", "-"),
            "sequence": value.get("sequence") or 1,
            "chapter_hint": value.get("chapter_hint"),
            "pov_character_id": value.get("pov"),
            "time_and_location": value.get("time_and_location"),
            "what_happens": value.get("title") or raw_outcome or "TBD",
            "goal": value.get("goal"),
            "conflict": value.get("conflict"),
            "turning_point": value.get("turning_point"),
            "outcome": outcome,
            "exit_condition": raw_outcome or value.get("turning_point") or "TBD",
            "information_delta": _as_list(value.get("information_delta")),
            "character_state_delta": _as_list(value.get("character_state_delta")),
            "required_canon_refs": value.get("required_canon_ids", []),
            "forbidden_fact_refs": value.get("forbidden_facts", []),
            "story_thread_actions": value.get("story_thread_actions", []),
            "estimated_words": value.get("estimated_words"),
            "source_refs": [],
        }


class ScenePrototypeBeat(ContractModel):
    beat_id: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=4000)
    opposition_or_complication: str = Field(min_length=1, max_length=4000)
    pov_response: str = Field(min_length=1, max_length=4000)
    state_change: str = Field(min_length=1, max_length=4000)


class SceneExpansionRecord(ContractModel):
    scene_id: str = Field(min_length=1, max_length=160)
    entry_state: str = Field(min_length=1, max_length=4000)
    pov_intention: str = Field(min_length=1, max_length=4000)
    beats: list[ScenePrototypeBeat] = Field(min_length=1, max_length=200)
    key_dialogue_fragments: list[str] = Field(default_factory=list, max_length=200)
    sensory_or_emotional_focus: list[str] = Field(default_factory=list, max_length=200)
    turning_point: str = Field(min_length=1, max_length=4000)
    exit_state: str = Field(min_length=1, max_length=4000)
    continuity_notes: list[str] = Field(default_factory=list, max_length=200)
    scene_contract_deviations: list[str] = Field(default_factory=list, max_length=200)
    recommendation: Literal["keep", "redesign", "merge", "delete"]
    recommendation_reason: str = Field(min_length=1, max_length=4000)
    source_refs: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "entry_state" in value:
            return value
        beats = value.get("beats")
        if not isinstance(beats, list):
            return value
        migrated_beats = [
            {
                "beat_id": f"B{index}",
                "action": str(beat),
                "opposition_or_complication": "TBD",
                "pov_response": "TBD",
                "state_change": "TBD",
            }
            for index, beat in enumerate(beats, start=1)
        ]
        return {
            "scene_id": value.get("scene_id"),
            "entry_state": "TBD",
            "pov_intention": "TBD",
            "beats": migrated_beats,
            "key_dialogue_fragments": [],
            "sensory_or_emotional_focus": _as_list(value.get("emotional_change")),
            "turning_point": migrated_beats[-1]["action"] if migrated_beats else "TBD",
            "exit_state": value.get("chapter_plan") or "TBD",
            "continuity_notes": [],
            "scene_contract_deviations": [],
            "recommendation": "keep",
            "recommendation_reason": value.get("chapter_plan") or "TBD",
            "source_refs": [],
        }


class ManuscriptSceneCoverage(ContractModel):
    goal: str = Field(min_length=1, max_length=4000)
    conflict: str = Field(min_length=1, max_length=4000)
    turning_point: str = Field(min_length=1, max_length=4000)
    outcome: str = Field(min_length=1, max_length=4000)
    missing_elements: list[str] = Field(default_factory=list, max_length=200)


class ManuscriptFactCandidate(ContractModel):
    claim: str = Field(min_length=1, max_length=4000)
    entity_refs: list[str] = Field(default_factory=list, max_length=200)
    reason_introduced: str = Field(min_length=1, max_length=4000)
    status: Literal["proposal"] = "proposal"


class DesignDeviationProposal(ContractModel):
    target_artifact_ref: str = Field(min_length=1, max_length=500)
    current_design: str = Field(min_length=1, max_length=4000)
    proposed_change: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=4000)
    downstream_impact: list[str] = Field(default_factory=list, max_length=200)


class ManuscriptSceneDraftContract(ContractModel):
    scene_id: str = Field(min_length=1, max_length=160)
    manuscript_prose: str = Field(min_length=1, max_length=300000)
    entry_state_observed: list[str] = Field(default_factory=list, max_length=200)
    exit_state_produced: list[str] = Field(default_factory=list, max_length=200)
    scene_contract_coverage: ManuscriptSceneCoverage
    new_fact_candidates: list[ManuscriptFactCandidate] = Field(default_factory=list, max_length=200)
    design_deviation_proposals: list[DesignDeviationProposal] = Field(
        default_factory=list, max_length=200
    )
    continuity_questions: list[str] = Field(default_factory=list, max_length=200)
    source_refs: list[str] = Field(default_factory=list, max_length=200)


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


STEP_CONTRACTS = {
    1: OneSentenceContract,
    2: OneParagraphContract,
    3: CharacterSummaryContract,
    4: OnePageSynopsisContract,
    5: CharacterViewpointsContract,
    6: ExpandedSynopsisContract,
    10: ManuscriptSceneDraftContract,
}


RECORD_CONTRACTS = {
    6: ExpandedSynopsisBlock,
    8: SceneListRecord,
    9: SceneExpansionRecord,
}


RECORD_STEP_NUMBERS = frozenset({6, 7, 8, 9})
