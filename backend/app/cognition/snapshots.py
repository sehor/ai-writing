from dataclasses import dataclass, field

from app.cognition.interfaces import ContextPacket, ProjectCognitionSnapshot, WritingScope
from app.data import WritingDataStore
from app.llm_wiki.interfaces import WikiContextQuery, WikiContextResult, WikiEvidence
from app.models import (
    CanonEntity,
    ManuscriptScene,
    MemoryRecord,
    ProjectSummary,
    SceneContract,
    StoryFact,
    StoryThread,
)
from app.text_utils import truncate


@dataclass(frozen=True)
class NarrativeSnapshot:
    """Scene-safe generation context assembled from application-owned state.

    This is the single entry point for prose-generation context. It deliberately
    carries structured application records instead of raw Snowflake Step 8/9
    artifacts, and it limits observed prose to positions before the target scene.
    """

    project: ProjectSummary
    scene: SceneContract
    canon_entities: list[CanonEntity] = field(default_factory=list)
    memory_records: list[MemoryRecord] = field(default_factory=list)
    manuscript_scenes: list[ManuscriptScene] = field(default_factory=list)
    world_truth: list[StoryFact] = field(default_factory=list)
    reader_knowledge: list[StoryFact] = field(default_factory=list)
    pov_knowledge: list[StoryFact] = field(default_factory=list)
    active_threads: list[StoryThread] = field(default_factory=list)
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

        project_snapshot = ProjectCognitionSnapshot(
            project=project,
            # Step 8/9 prose-planning artifacts are intentionally not forwarded
            # into scene generation context. Cognition modules receive only the
            # state types needed for scene-safe retrieval.
            artifacts=[],
            canon_entities=data_store.list_canon_entities(project_id),
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
        active_threads = [
            thread
            for thread in data_store.list_story_threads(project_id)
            if thread.status in {"planted", "developing", "dormant"}
            and (thread.planted_at is None or thread.planted_at <= scene.sequence)
        ]

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
                    # Cross-scene observed prose must remain visible. The story
                    # position is the visibility boundary, not a scene-id scope.
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
            canon_entities=project_snapshot.canon_entities,
            memory_records=memory_records,
            manuscript_scenes=manuscript_scenes,
            world_truth=world_truth,
            reader_knowledge=reader_knowledge,
            pov_knowledge=pov_knowledge,
            active_threads=active_threads,
            cognition_context=cognition_context,
            wiki_context=wiki_context,
        )

    def as_project_snapshot(self) -> ProjectCognitionSnapshot:
        """Compatibility view without leaking non-temporal legacy Canon state."""
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
            story_thread_events=[],
        )

    def render_generation_context(self) -> str:
        """Render the structured scene snapshot into one provider-safe prompt."""
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

        if self.world_truth:
            reader_ids = {item.id for item in self.reader_knowledge}
            pov_ids = {item.id for item in self.pov_knowledge}
            reader_visible = [fact for fact in self.world_truth if fact.id in reader_ids]
            protected_count = len(self.world_truth) - len(reader_visible)
            sections.extend(["", "Temporal story facts visible to the reader:"])
            if reader_visible:
                sections.append(
                    "\n".join(
                        f"- {fact.subject} {fact.predicate} {fact.value} | "
                        f"POV={'known' if fact.id in pov_ids else 'not-confirmed'}"
                        for fact in reader_visible
                    )
                )
            else:
                sections.append("- No reader-visible temporal facts at this scene.")
            if protected_count:
                sections.append(
                    f"Protected world facts withheld from prose context: {protected_count}. "
                    "Do not invent or reveal their values; follow Scene Contract and thread reveal constraints."
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
        # Scene drafting only accepts observed evidence with a proven story
        # position before the target. Unknown-position evidence is not safe
        # enough to distinguish past context from a future reveal.
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


def build_project_snapshot(
    project_id: str,
    data_store: WritingDataStore,
) -> ProjectCognitionSnapshot:
    project = data_store.get_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    story_threads = data_store.list_story_threads(project_id)
    story_thread_events = [
        event
        for thread in story_threads
        for event in data_store.list_story_thread_events(project_id, thread.id)
    ]
    return ProjectCognitionSnapshot(
        project=project,
        artifacts=data_store.list_snowflake_artifacts(project_id),
        canon_entities=data_store.list_canon_entities(project_id),
        scenes=data_store.list_scene_contracts(project_id),
        memory_records=data_store.list_memory_records(project_id),
        manuscript_scenes=data_store.list_manuscript_scenes(project_id),
        story_threads=story_threads,
        story_thread_events=story_thread_events,
    )
