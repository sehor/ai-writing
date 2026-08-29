from app.models import (
    CanonEntity,
    GraphEdge,
    GraphNode,
    GraphRisk,
    MemoryRecord,
    SceneContract,
    SnowflakeArtifact,
    StoryThread,
    StoryThreadEvent,
)
from app.text_utils import truncate


def build_graph_nodes(
    project_id: str,
    project_title: str,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
    story_threads: list[StoryThread] | None = None,
) -> list[GraphNode]:
    nodes = [
        GraphNode(
            id=f"project:{project_id}",
            label=project_title,
            node_type="project",
            status="active",
        )
    ]
    nodes.extend(
        GraphNode(
            id=f"artifact:{artifact.step_number}",
            label=f"Step {artifact.step_number}: {artifact.artifact}",
            node_type="snowflake_artifact",
            status="saved",
        )
        for artifact in artifacts
    )
    nodes.extend(
        GraphNode(
            id=f"canon:{entity.id}",
            label=entity.name,
            node_type="canon_entity",
            status=entity.entity_type,
        )
        for entity in canon_entities
    )
    nodes.extend(
        GraphNode(
            id=f"scene:{scene.id}",
            label=f"{scene.sequence}. {scene.title}",
            node_type="scene",
            status=scene.pov or "No POV",
        )
        for scene in scenes
    )
    nodes.extend(
        GraphNode(
            id=f"memory:{record.id}",
            label=record.title,
            node_type="memory_record",
            status=record.record_type,
        )
        for record in memory_records
    )
    nodes.extend(
        GraphNode(
            id=f"thread:{thread.id}",
            label=thread.title,
            node_type="story_thread",
            status=f"{thread.thread_type}:{thread.status}",
        )
        for thread in (story_threads or [])
    )
    return nodes


def build_graph_edges(
    project_id: str,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
    story_threads: list[StoryThread] | None = None,
    story_thread_events: list[StoryThreadEvent] | None = None,
) -> list[GraphEdge]:
    project_node = f"project:{project_id}"
    edges: list[GraphEdge] = []
    edges.extend(
        GraphEdge(
            source=project_node,
            target=f"artifact:{artifact.step_number}",
            edge_type="contains",
            label="Snowflake",
        )
        for artifact in artifacts
    )
    edges.extend(
        GraphEdge(
            source=project_node,
            target=f"canon:{entity.id}",
            edge_type="contains",
            label=entity.entity_type,
        )
        for entity in canon_entities
    )
    edges.extend(
        GraphEdge(
            source=project_node,
            target=f"scene:{scene.id}",
            edge_type="contains",
            label="Scene contract",
        )
        for scene in scenes
    )
    edges.extend(
        GraphEdge(
            source=project_node,
            target=f"memory:{record.id}",
            edge_type="contains",
            label=record.record_type,
        )
        for record in memory_records
    )
    edges.extend(
        GraphEdge(
            source=project_node,
            target=f"thread:{thread.id}",
            edge_type="contains",
            label=thread.thread_type,
        )
        for thread in (story_threads or [])
    )
    edges.extend(
        GraphEdge(
            source=f"thread:{event.thread_id}",
            target=f"scene:{event.scene_id}",
            edge_type="references",
            label=event.action,
        )
        for event in (story_thread_events or [])
    )

    artifact_steps = {artifact.step_number for artifact in artifacts}
    edges.extend(
        GraphEdge(
            source=f"scene:{scene.id}",
            target=f"artifact:{scene.source_artifact_step}",
            edge_type="depends_on",
            label="source artifact",
        )
        for scene in scenes
        if scene.source_artifact_step in artifact_steps
    )

    for scene in scenes:
        scene_text = searchable_scene_text(scene)
        for entity in canon_entities:
            if entity.name and entity.name.lower() in scene_text:
                edges.append(
                    GraphEdge(
                        source=f"scene:{scene.id}",
                        target=f"canon:{entity.id}",
                        edge_type="references",
                        label="mentions Canon",
                    )
                )

    for record in memory_records:
        source_ref = record.source_ref.strip().lower()
        if not source_ref:
            continue
        for scene in scenes:
            if source_ref in scene.id.lower() or source_ref in scene.title.lower():
                edges.append(
                    GraphEdge(
                        source=f"memory:{record.id}",
                        target=f"scene:{scene.id}",
                        edge_type="informs",
                        label="source ref",
                    )
                )
        for artifact in artifacts:
            artifact_ref = f"step {artifact.step_number}"
            if source_ref == artifact.artifact.lower() or source_ref == artifact_ref:
                edges.append(
                    GraphEdge(
                        source=f"memory:{record.id}",
                        target=f"artifact:{artifact.step_number}",
                        edge_type="informs",
                        label="source ref",
                    )
                )

    return dedupe_edges(edges)


def build_graph_risks(
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
    story_threads: list[StoryThread] | None = None,
    story_thread_events: list[StoryThreadEvent] | None = None,
) -> list[GraphRisk]:
    risks: list[GraphRisk] = []
    artifact_steps = {artifact.step_number for artifact in artifacts}

    if 8 in artifact_steps and not scenes:
        risks.append(
            GraphRisk(
                id="missing-scene-contracts",
                severity="critical",
                title="Scene list has no structured contracts",
                detail="Snowflake step 8 exists, but no Scene Contracts are recorded for manuscript compilation.",
                source_id="artifact:8",
            )
        )

    for scene in scenes:
        required_fields = [
            ("pov", "POV"),
            ("goal", "goal"),
            ("conflict", "conflict"),
            ("turning_point", "turning point"),
        ]
        for field_name, label in required_fields:
            if not getattr(scene, field_name):
                risks.append(
                    GraphRisk(
                        id=f"scene-{scene.id}-missing-{field_name}",
                        severity="critical",
                        title=f"Scene is missing {label}",
                        detail=f"{scene.title} needs a {label} before reliable manuscript compilation.",
                        source_id=f"scene:{scene.id}",
                    )
                )
        if not scene.required_canon:
            risks.append(
                GraphRisk(
                    id=f"scene-{scene.id}-missing-required-canon",
                    severity="warning",
                    title="Scene has no required Canon",
                    detail=f"{scene.title} does not list Canon facts it must preserve.",
                    source_id=f"scene:{scene.id}",
                )
            )

        if scene.source_artifact_step not in artifact_steps:
            risks.append(
                GraphRisk(
                    id=f"scene-{scene.id}-missing-source",
                    severity="warning",
                    title="Scene source artifact is missing",
                    detail=f"{scene.title} depends on Snowflake step {scene.source_artifact_step}, but that artifact is not saved.",
                    source_id=f"scene:{scene.id}",
                )
            )
        if scene.open_threads:
            risks.append(
                GraphRisk(
                    id=f"scene-{scene.id}-open-threads",
                    severity="info",
                    title="Open thread requires review",
                    detail=f"{scene.title}: {truncate(scene.open_threads, 220)}",
                    source_id=f"scene:{scene.id}",
                )
            )

    referenced_canon_ids = {
        entity.id
        for scene in scenes
        for entity in canon_entities
        if entity.name and entity.name.lower() in searchable_scene_text(scene)
    }

    for entity in canon_entities:
        if entity.id not in referenced_canon_ids and scenes:
            risks.append(
                GraphRisk(
                    id=f"canon-{entity.id}-unreferenced",
                    severity="warning",
                    title="Canon entity is not used by any scene",
                    detail=f"{entity.name} is recorded in Canon but is not mentioned in current Scene Contracts.",
                    source_id=f"canon:{entity.id}",
                )
            )
        if not entity.constraints and not entity.current_state:
            risks.append(
                GraphRisk(
                    id=f"canon-{entity.id}-thin-state",
                    severity="info",
                    title="Canon entity has thin state",
                    detail=f"{entity.name} has no current state or constraints, so future checks have little to enforce.",
                    source_id=f"canon:{entity.id}",
                )
            )

    for record in memory_records:
        if not record.scope and not record.tags:
            risks.append(
                GraphRisk(
                    id=f"memory-{record.id}-unscoped",
                    severity="info",
                    title="Memory record is unscoped",
                    detail=f"{record.title} has no scope or tags, making retrieval less precise.",
                    source_id=f"memory:{record.id}",
                )
            )

    risks.extend(build_director_risks(story_threads or [], story_thread_events or [], scenes))
    return risks


def build_director_risks(
    story_threads: list[StoryThread],
    events: list[StoryThreadEvent],
    scenes: list[SceneContract],
) -> list[GraphRisk]:
    if not story_threads or not scenes:
        return []
    sequence_by_scene = {scene.id: scene.sequence for scene in scenes}
    current_sequence = max(sequence_by_scene.values())
    events_by_thread: dict[str, list[StoryThreadEvent]] = {}
    for event in events:
        events_by_thread.setdefault(event.thread_id, []).append(event)

    risks: list[GraphRisk] = []
    active_statuses = {"planted", "developing", "dormant"}
    for thread in story_threads:
        thread_events = events_by_thread.get(thread.id, [])
        event_positions = [
            sequence_by_scene[event.scene_id]
            for event in thread_events
            if event.scene_id in sequence_by_scene
        ]
        last_position = max(event_positions) if event_positions else thread.planted_at

        if (
            thread.status in active_statuses
            and thread.target_payoff_to is not None
            and current_sequence > thread.target_payoff_to
        ):
            overdue_by = current_sequence - thread.target_payoff_to
            risks.append(
                GraphRisk(
                    id=f"thread-{thread.id}-overdue",
                    severity="critical" if thread.importance >= 4 else "warning",
                    title=f"Story thread payoff is overdue: {thread.title}",
                    detail=(
                        f"Target payoff window ended at scene {thread.target_payoff_to}; "
                        f"the project is at scene {current_sequence} ({overdue_by} scene(s) late)."
                    ),
                    source_id=f"thread:{thread.id}",
                )
            )

        if (
            thread.status in active_statuses
            and last_position is not None
            and current_sequence - last_position >= 5
        ):
            risks.append(
                GraphRisk(
                    id=f"thread-{thread.id}-stalled",
                    severity="warning" if thread.importance >= 3 else "info",
                    title=f"Story thread has not advanced recently: {thread.title}",
                    detail=(
                        f"Its latest structured event is at scene {last_position}; "
                        f"{current_sequence - last_position} scenes have passed without reinforcement."
                    ),
                    source_id=f"thread:{thread.id}",
                )
            )

        payoff_positions = [
            sequence_by_scene[event.scene_id]
            for event in thread_events
            if event.action == "payoff" and event.scene_id in sequence_by_scene
        ]
        if (
            payoff_positions
            and thread.importance >= 4
            and thread.target_payoff_from is not None
            and min(payoff_positions) < thread.target_payoff_from
        ):
            paid_at = min(payoff_positions)
            risks.append(
                GraphRisk(
                    id=f"thread-{thread.id}-early-payoff",
                    severity="warning",
                    title=f"High-importance thread may resolve too early: {thread.title}",
                    detail=(
                        f"Structured payoff occurs at scene {paid_at}, before the target "
                        f"window opens at scene {thread.target_payoff_from}."
                    ),
                    source_id=f"thread:{thread.id}",
                )
            )

    high_importance_ids = {thread.id for thread in story_threads if thread.importance >= 4}
    advanced_positions = {
        sequence_by_scene[event.scene_id]
        for event in events
        if event.thread_id in high_importance_ids
        and event.scene_id in sequence_by_scene
        and event.action in {"reinforce", "escalate", "partial_payoff", "payoff"}
    }
    ordered_positions = sorted(sequence_by_scene.values())
    scene_by_position = {scene.sequence: scene for scene in scenes}
    if len(ordered_positions) >= 4:
        if high_importance_ids:
            for index in range(len(ordered_positions) - 3):
                window = ordered_positions[index : index + 4]
                if not any(position in advanced_positions for position in window):
                    risks.append(
                        GraphRisk(
                            id=f"director-mainline-stall-{window[0]}-{window[-1]}",
                            severity="warning",
                            title="Four-scene stretch lacks high-importance thread advancement",
                            detail=(
                                f"Scenes {window[0]}-{window[-1]} contain no structured reinforce, "
                                "escalate, partial payoff, or payoff event for an importance 4-5 thread."
                            ),
                            source_id=f"scene:{scene_by_position[window[-1]].id}",
                        )
                    )
                    break

        intensity_markers = (
            "reveal",
            "death",
            "dies",
            "kill",
            "betray",
            "explode",
            "final",
            "揭露",
            "真相",
            "死亡",
            "杀",
            "背叛",
            "爆炸",
            "决战",
        )
        for index in range(len(ordered_positions) - 3):
            window = ordered_positions[index : index + 4]
            intense = []
            for position in window:
                scene = scene_by_position[position]
                text = f"{scene.conflict} {scene.turning_point}".lower()
                if any(marker in text for marker in intensity_markers):
                    intense.append(position)
            if len(intense) >= 3:
                risks.append(
                    GraphRisk(
                        id=f"director-intensity-cluster-{window[0]}-{window[-1]}",
                        severity="warning",
                        title="High-intensity turning points are tightly clustered",
                        detail=(
                            f"Scenes {window[0]}-{window[-1]} contain {len(intense)} high-intensity "
                            "conflict/turning-point markers. Check whether the pacing leaves enough "
                            "recovery and setup between major beats."
                        ),
                        source_id=f"scene:{scene_by_position[window[-1]].id}",
                    )
                )
                break
    return risks


def searchable_scene_text(scene: SceneContract) -> str:
    return " ".join(
        [
            scene.id,
            scene.title,
            scene.pov,
            scene.goal,
            scene.conflict,
            scene.turning_point,
            scene.required_canon,
            scene.forbidden_facts,
            scene.open_threads,
        ]
    ).lower()


def dedupe_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[GraphEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.edge_type, edge.label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped
