from __future__ import annotations

from dataclasses import dataclass, field

from app.cognition.interfaces import ContextPacket, ProjectCognitionSnapshot, WritingScope
from app.data import WritingDataStore
from app.llm_wiki.interfaces import WikiContextQuery, WikiContextResult, WikiEvidence
from app.models import (
    CanonEntity,
    ManuscriptScene,
    MemoryRecord,
    NarrativeRelation,
    ProjectSummary,
    SceneContract,
    StoryFact,
    StoryThread,
    StoryThreadEvent,
)
from app.narrative.graph import NarrativeGraph
from app.narrative.projector import NarrativeGraphProjector
from app.text_utils import truncate

_ACTIVE_THREAD_STATUSES = {"planted", "developing", "dormant"}
_THREAD_DEVELOPMENT_ACTIONS = {"reinforce", "misdirect", "escalate", "partial_payoff"}


@dataclass(frozen=True)
class NarrativeSnapshot:
    """Scene-safe context deterministically derived from authoritative SQLite state.

    The snapshot is never persisted. Temporal facts come from the Narrative Domain,
    narrative relations come through the P1 graph projection, and prose-facing output
    exposes only values that are safe for both the reader and the current POV.
    """

    project: ProjectSummary
    scene: SceneContract
    canon_entities: list[CanonEntity] = field(default_factory=list)
    memory_records: list[MemoryRecord] = field(default_factory=list)
    manuscript_scenes: list[ManuscriptScene] = field(default_factory=list)
    world_truth: list[StoryFact] = field(default_factory=list)
    reader_knowledge: list[StoryFact] = field(default_factory=list)
    pov_knowledge: list[StoryFact] = field(default_factory=list)
    related_character_knowledge: dict[str, list[StoryFact]] = field(default_factory=dict)
    narrative_relations: list[NarrativeRelation] = field(default_factory=list)
    story_threads: list[StoryThread] = field(default_factory=list)
    active_threads: list[StoryThread] = field(default_factory=list)
    story_thread_events: list[StoryThreadEvent] = field(default_factory=list)
    thread_event_history: list[StoryThreadEvent] = field(default_factory=list)
    latest_scene_sequence: int = 0
    scene_sequence_by_id: dict[str, int] = field(default_factory=dict)
    safe_future_constraints: list[str] = field(default_factory=list)
    future_fact_ids: list[str] = field(default_factory=list)
    future_relation_ids: list[str] = field(default_factory=list)
    cognition_context: list[ContextPacket] = field(default_factory=list)
    wiki_context: WikiContextResult = field(
        default_factory=lambda: WikiContextResult(summary="No LLM Wiki context loaded.")
    )

    @classmethod
    def for_scene(
        cls,
        *,
        project_id: str,
        scene_id: str,
        data_store: WritingDataStore,
        cognition=None,
        llm_wiki=None,
    ) -> "NarrativeSnapshot":
        project = data_store.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        scene = data_store.get_scene_contract(project_id, scene_id)
        if scene is None:
            raise ValueError(f"Scene contract not found: {scene_id}")

        scenes = data_store.list_scene_contracts(project_id)
        sequence_by_id = {item.id: item.sequence for item in scenes}
        memory_records = _visible_memory_records(
            data_store.list_memory_records(project_id),
            sequence_by_id,
            scene.sequence,
            scene.pov,
        )
        manuscript_scenes = _prior_manuscript_scenes(
            data_store.list_manuscript_scenes(project_id),
            sequence_by_id,
            scene.sequence,
        )
        canon_entities = data_store.list_canon_entities(project_id)

        project_snapshot = ProjectCognitionSnapshot(
            project=project,
            # Step 8/9 prose-planning artifacts remain outside scene generation.
            artifacts=[],
            canon_entities=canon_entities,
            scenes=scenes,
            memory_records=memory_records,
            manuscript_scenes=manuscript_scenes,
        )
        world_truth = data_store.list_story_facts_at(project_id, scene.sequence)
        reader_knowledge = data_store.list_reader_facts_at(project_id, scene.sequence)
        pov_knowledge = (
            data_store.list_character_facts_at(project_id, scene.pov, scene.sequence)
            if scene.pov
            else []
        )

        graph = NarrativeGraphProjector(data_store).project(project_id)
        narrative_relations, future_relation_ids = _relations_for_scene(
            graph,
            project_id,
            scene.sequence,
        )
        related_character_knowledge = {
            character: data_store.list_character_facts_at(
                project_id,
                character,
                scene.sequence,
            )
            for character in _related_characters(narrative_relations, scene.pov)
        }
        future_fact_ids = sorted(
            fact.id
            for fact in data_store.list_story_facts(project_id)
            if fact.status in {"planned", "confirmed"} and fact.valid_from_scene > scene.sequence
        )
        story_threads = data_store.list_story_threads(project_id)
        active_threads, story_thread_events, thread_event_history = _threads_for_scene(
            data_store,
            project_id,
            scenes,
            scene.sequence,
            story_threads=story_threads,
        )
        safe_future_constraints = _safe_future_constraints(scene, active_threads)

        cognition_context = (
            cognition.prepare_context(
                project_snapshot,
                WritingScope(kind="scene", ref=scene.id, instruction=scene.title),
            )
            if cognition is not None
            else []
        )
        if llm_wiki is not None:
            raw_wiki_context = llm_wiki.retrieve_context(
                WikiContextQuery(
                    project_id=project_id,
                    snowflake_step=10,
                    instruction=scene.title,
                    # Cross-scene observed prose remains visible. Story position,
                    # not scene-id scope, is the spoiler boundary.
                    scope="",
                    story_position=scene.sequence,
                    spoiler_horizon=scene.sequence,
                )
            )
            wiki_context = _scene_safe_wiki_context(raw_wiki_context, scene.sequence)
        else:
            wiki_context = WikiContextResult(summary="LLM Wiki context not requested.")

        return cls(
            project=project,
            scene=scene,
            canon_entities=canon_entities,
            memory_records=memory_records,
            manuscript_scenes=manuscript_scenes,
            world_truth=world_truth,
            reader_knowledge=reader_knowledge,
            pov_knowledge=pov_knowledge,
            related_character_knowledge=related_character_knowledge,
            narrative_relations=narrative_relations,
            story_threads=story_threads,
            active_threads=active_threads,
            story_thread_events=story_thread_events,
            thread_event_history=thread_event_history,
            latest_scene_sequence=max((item.sequence for item in scenes), default=scene.sequence),
            scene_sequence_by_id=sequence_by_id,
            safe_future_constraints=safe_future_constraints,
            future_fact_ids=future_fact_ids,
            future_relation_ids=future_relation_ids,
            cognition_context=cognition_context,
            wiki_context=wiki_context,
        )

    def as_project_snapshot(self) -> ProjectCognitionSnapshot:
        """Compatibility view for legacy cognition/reference consumers."""
        safe_canon = [
            entity.model_copy(update={"current_state": "", "last_seen": "", "timeline_notes": ""})
            for entity in self.canon_entities
        ]
        return ProjectCognitionSnapshot(
            project=self.project,
            artifacts=[],
            canon_entities=safe_canon,
            scenes=[self.scene],
            memory_records=self.memory_records,
            manuscript_scenes=self.manuscript_scenes,
            story_threads=self.active_threads,
            story_thread_events=self.story_thread_events,
        )

    def render_generation_context(self) -> str:
        """Render only prose-safe values while preserving explicit isolation guards."""
        scene = self.scene
        sections = [
            f"Project: {self.project.title}",
            f"Scene: {scene.sequence}. {scene.title}",
            f"POV: {scene.pov or 'TBD'}",
            f"Goal: {scene.goal or 'TBD'}",
            f"Conflict: {scene.conflict or 'TBD'}",
            f"Turning Point: {scene.turning_point or 'TBD'}",
            f"Required Canon: {scene.required_canon or 'None listed'}",
            f"Forbidden Facts: {scene.forbidden_facts or 'None listed'}",
            f"Open Threads: {scene.open_threads or 'None listed'}",
        ]

        world_ids = {item.id for item in self.world_truth}
        reader_ids = {item.id for item in self.reader_knowledge}
        pov_ids = {item.id for item in self.pov_knowledge}
        visible_ids = reader_ids & pov_ids if scene.pov else reader_ids
        visible_facts = [fact for fact in self.world_truth if fact.id in visible_ids]
        reader_only_ids = reader_ids - pov_ids if scene.pov else set()
        pov_only_ids = pov_ids - reader_ids if scene.pov else set()
        reader_hidden_ids = world_ids - reader_ids

        sections.extend(["", "Scene-safe temporal facts:"])
        if visible_facts:
            sections.append(
                "\n".join(
                    f"- {fact.subject} {fact.predicate} {fact.value}" for fact in visible_facts
                )
            )
        else:
            sections.append("- No fact values are safe for prose at this scene.")

        isolation_lines = []
        if reader_hidden_ids:
            isolation_lines.extend(
                [
                    f"World facts not yet reader-visible: {len(reader_hidden_ids)}; values withheld.",
                    (
                        "Protected world facts withheld from prose context: "
                        f"{len(reader_hidden_ids)}."
                    ),
                ]
            )
        if scene.pov and reader_only_ids:
            isolation_lines.append(
                f"Reader-only facts withheld from POV context: {len(reader_only_ids)}."
            )
        if scene.pov and pov_only_ids:
            isolation_lines.append(
                f"POV-only facts withheld from reader context: {len(pov_only_ids)}."
            )
        if self.future_fact_ids:
            isolation_lines.append(
                f"Future story facts withheld from generation: {len(self.future_fact_ids)}."
            )
        if self.future_relation_ids:
            isolation_lines.append(
                "Future narrative relations withheld from generation: "
                f"{len(self.future_relation_ids)}."
            )
        if isolation_lines:
            sections.extend(["", "Knowledge / spoiler isolation:", "\n".join(isolation_lines)])

        if self.narrative_relations:
            sections.extend(
                [
                    "",
                    (
                        "Narrative Graph state: "
                        f"{len(self.narrative_relations)} current relation(s) retained structurally. "
                        "Raw relation details are not exposed to prose without knowledge scope."
                    ),
                ]
            )
        if self.canon_entities:
            sections.extend(
                [
                    "",
                    "Legacy Canon constraints (non-temporal fields only):",
                    "\n".join(
                        f"- {entity.entity_type}: {entity.name}"
                        + (f" | constraints={entity.constraints}" if entity.constraints else "")
                        for entity in self.canon_entities
                    ),
                ]
            )
        if self.active_threads:
            sections.extend(
                [
                    "",
                    "Active Story Threads:",
                    "\n".join(
                        f"- {thread.thread_type}: {thread.title} | status={thread.status} | "
                        f"payoff={thread.target_payoff_from or '?'}-{thread.target_payoff_to or '?'} | "
                        f"constraints={thread.reveal_constraints or 'none'}"
                        for thread in self.active_threads
                    ),
                ]
            )
        if self.story_thread_events:
            thread_by_id = {thread.id: thread for thread in self.active_threads}
            sections.extend(
                [
                    "",
                    "Earlier relevant Story Thread events:",
                    "\n".join(
                        (
                            f"- {thread_by_id[event.thread_id].title}: {event.action} "
                            f"| scene={event.scene_id}"
                        )
                        for event in self.story_thread_events
                        if event.thread_id in thread_by_id
                    ),
                ]
            )
        if self.safe_future_constraints:
            sections.extend(
                [
                    "",
                    "Safe future constraints (constraints only, never future facts):",
                    "\n".join(f"- {item}" for item in self.safe_future_constraints),
                ]
            )
        if self.memory_records:
            sections.extend(
                [
                    "",
                    "Relevant Memory / Style:",
                    "\n".join(
                        f"- {record.record_type}: {record.title} | {truncate(record.content, 1800)}"
                        for record in self.memory_records
                    ),
                ]
            )
        if self.manuscript_scenes:
            sections.extend(
                [
                    "",
                    "Earlier accepted manuscript:",
                    "\n\n".join(
                        f"## {item.title} v{item.version}\n{truncate(item.content, 2600)}"
                        for item in self.manuscript_scenes
                    ),
                ]
            )
        if self.cognition_context:
            sections.extend(
                [
                    "",
                    "Cognition context:",
                    "\n\n".join(
                        f"## {packet.module}: {packet.title}\n{truncate(packet.content, 2600)}"
                        for packet in self.cognition_context
                    ),
                ]
            )
        if self.wiki_context.evidence:
            sections.extend(
                [
                    "",
                    "Earlier observed continuity evidence:",
                    "\n\n".join(
                        f"## {item.title}\nSource: {item.source_ref}\n{truncate(item.excerpt, 2600)}"
                        for item in self.wiki_context.evidence
                    ),
                ]
            )
        return "\n".join(sections)


def _relations_for_scene(
    graph: NarrativeGraph,
    project_id: str,
    target_sequence: int,
) -> tuple[list[NarrativeRelation], list[str]]:
    active: list[NarrativeRelation] = []
    future_ids: list[str] = []
    for source, target, relation_id, metadata in graph.networkx.edges(keys=True, data=True):
        valid_from = int(metadata["valid_from"])
        valid_to = metadata.get("valid_to")
        status = str(metadata.get("status", ""))
        if status in {"planned", "confirmed"} and valid_from > target_sequence:
            future_ids.append(str(relation_id))
        if status != "confirmed":
            continue
        if valid_from > target_sequence:
            continue
        if valid_to is not None and int(valid_to) < target_sequence:
            continue
        active.append(
            NarrativeRelation(
                id=str(relation_id),
                project_id=str(metadata.get("project_id") or project_id),
                source=str(source),
                target=str(target),
                relation=str(metadata["relation"]),
                valid_from=valid_from,
                valid_to=int(valid_to) if valid_to is not None else None,
                confidence=float(metadata.get("confidence", 1.0)),
                source_ref=str(metadata.get("source_ref", "")),
                status=status,
            )
        )
    active.sort(
        key=lambda item: (
            item.source,
            item.target,
            item.relation,
            item.valid_from,
            item.id,
        )
    )
    return active, sorted(future_ids)


def _related_characters(
    relations: list[NarrativeRelation],
    pov: str,
) -> list[str]:
    normalized_pov = pov.strip().casefold()
    if not normalized_pov:
        return []
    related: set[str] = set()
    for relation in relations:
        source = _character_label(relation.source)
        target = _character_label(relation.target)
        if source == normalized_pov and target and target != normalized_pov:
            related.add(target)
        if target == normalized_pov and source and source != normalized_pov:
            related.add(source)
    return sorted(related)


def _character_label(node_id: str) -> str:
    node_type, separator, label = node_id.partition(":")
    if not separator or node_type.casefold() != "character":
        return ""
    return label.strip().casefold()


def _threads_for_scene(
    data_store: WritingDataStore,
    project_id: str,
    scenes: list[SceneContract],
    target_sequence: int,
    *,
    story_threads: list[StoryThread] | None = None,
) -> tuple[list[StoryThread], list[StoryThreadEvent], list[StoryThreadEvent]]:
    sequence_by_id = {scene.id: scene.sequence for scene in scenes}
    active_threads: list[StoryThread] = []
    visible_events: list[tuple[int, StoryThreadEvent]] = []
    history_events: list[tuple[int, StoryThreadEvent]] = []

    for thread in (
        story_threads if story_threads is not None else data_store.list_story_threads(project_id)
    ):
        events_with_sequence = [
            (sequence_by_id[event.scene_id], event)
            for event in data_store.list_story_thread_events(project_id, thread.id)
            if event.scene_id in sequence_by_id
        ]
        events_with_sequence.sort(key=lambda item: (item[0], item[1].id))
        prior_events = [item for item in events_with_sequence if item[0] < target_sequence]
        history_events.extend(prior_events)
        # Abandonment has no scene timestamp in the current domain, so the safe
        # generation interpretation is to keep it out of every scene context.
        # Director analytics still receives the raw thread plus prior events and
        # can explain that historical abandonment timing is indeterminate.
        if thread.status == "abandoned":
            continue
        planted_at = thread.planted_at
        if planted_at is None:
            planted_sequences = [
                sequence for sequence, event in events_with_sequence if event.action == "plant"
            ]
            planted_at = min(planted_sequences) if planted_sequences else None
        if planted_at is None or planted_at > target_sequence:
            continue
        if any(event.action == "payoff" for _, event in prior_events):
            continue

        status = "planted"
        if any(event.action in _THREAD_DEVELOPMENT_ACTIONS for _, event in prior_events):
            status = "developing"
        elif thread.status == "dormant":
            status = "dormant"
        if status not in _ACTIVE_THREAD_STATUSES:
            continue

        active_threads.append(
            thread.model_copy(update={"status": status, "planted_at": planted_at})
        )
        visible_events.extend(prior_events)

    visible_events.sort(key=lambda item: (item[0], item[1].thread_id, item[1].id))
    history_events.sort(key=lambda item: (item[0], item[1].thread_id, item[1].id))
    return (
        active_threads,
        [event for _, event in visible_events],
        [event for _, event in history_events],
    )


def _safe_future_constraints(
    scene: SceneContract,
    active_threads: list[StoryThread],
) -> list[str]:
    constraints: list[str] = []
    if scene.forbidden_facts:
        constraints.append(f"Scene Contract: {scene.forbidden_facts}")
    for thread in active_threads:
        if thread.reveal_constraints:
            constraints.append(f'Story Thread "{thread.title}": {thread.reveal_constraints}')
    return constraints


def _visible_memory_records(
    records: list[MemoryRecord],
    sequence_by_id: dict[str, int],
    target_sequence: int,
    pov: str,
) -> list[MemoryRecord]:
    visible: list[MemoryRecord] = []
    normalized_pov = pov.strip().lower()
    for record in records:
        scoped_sequence = sequence_by_id.get(record.scope)
        if scoped_sequence is not None and scoped_sequence > target_sequence:
            continue
        visible.append(record)

    def score(record: MemoryRecord) -> tuple[int, int, str]:
        scoped_sequence = sequence_by_id.get(record.scope)
        text = f"{record.title} {record.scope} {record.tags}".lower()
        priority = 0
        if record.record_type == "style_rule":
            priority += 40
        if record.record_type == "voice_sample" and normalized_pov and normalized_pov in text:
            priority += 35
        if record.record_type == "prose_sample":
            priority += 20
        if scoped_sequence is not None:
            priority += max(0, 18 - (target_sequence - scoped_sequence))
        return (-priority, -(scoped_sequence or 0), record.title.lower())

    visible.sort(key=score)
    return visible[:24]


def _prior_manuscript_scenes(
    scenes: list[ManuscriptScene],
    sequence_by_id: dict[str, int],
    target_sequence: int,
) -> list[ManuscriptScene]:
    visible = [
        item
        for item in scenes
        if sequence_by_id.get(item.scene_id, target_sequence + 1) < target_sequence
    ]
    visible.sort(key=lambda item: sequence_by_id.get(item.scene_id, 9999))
    return visible


def _scene_safe_wiki_context(context: WikiContextResult, target_sequence: int) -> WikiContextResult:
    evidence: list[WikiEvidence] = []
    for item in context.evidence:
        if item.knowledge_class != "observed":
            continue
        if item.story_position is None or item.story_position >= target_sequence:
            continue
        evidence.append(item)
    source_refs = {item.source_ref for item in evidence}
    constraints = [
        item
        for item in context.constraints
        if not item.source_refs or any(source_ref in source_refs for source_ref in item.source_refs)
    ]
    return WikiContextResult(
        summary=f"Scene-safe continuity evidence: {len(evidence)} observed source(s).",
        evidence=evidence,
        constraints=constraints,
    )
