from pathlib import Path

from app.cognition.interfaces import ProjectCognitionSnapshot
from app.models import (
    CanonEntity,
    GraphAnalysisResponse,
    GraphAnalysisSummary,
    GraphEdge,
    GraphNode,
    GraphRisk,
    MemoryRecord,
    SceneContract,
    SnowflakeArtifact,
)


class LocalInfraGraphModule:
    name = "infra_graph"

    def __init__(self, modules_root: Path):
        self.modules_root = modules_root

    def project_path(self, project_id: str) -> Path:
        return self.modules_root / project_id / "modules" / self.name

    def analyze(self, snapshot: ProjectCognitionSnapshot) -> GraphAnalysisResponse:
        nodes = build_nodes(
            snapshot.project.id,
            snapshot.project.title,
            snapshot.artifacts,
            snapshot.canon_entities,
            snapshot.scenes,
            snapshot.memory_records,
        )
        edges = build_edges(
            snapshot.project.id,
            snapshot.artifacts,
            snapshot.canon_entities,
            snapshot.scenes,
            snapshot.memory_records,
        )
        risks = build_risks(
            snapshot.artifacts,
            snapshot.canon_entities,
            snapshot.scenes,
            snapshot.memory_records,
        )
        summary = GraphAnalysisSummary(
            node_count=len(nodes),
            edge_count=len(edges),
            risk_count=len(risks),
            critical_count=sum(1 for risk in risks if risk.severity == "critical"),
            warning_count=sum(1 for risk in risks if risk.severity == "warning"),
            unresolved_thread_count=sum(1 for scene in snapshot.scenes if scene.open_threads),
            canon_reference_count=sum(
                1 for edge in edges if edge.edge_type == "references" and edge.target.startswith("canon:")
            ),
        )
        return GraphAnalysisResponse(
            project_id=snapshot.project.id,
            summary=summary,
            nodes=nodes,
            edges=edges,
            risks=risks,
        )


def build_nodes(
    project_id: str,
    project_title: str,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
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
    return nodes


def build_edges(
    project_id: str,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
) -> list[GraphEdge]:
    project_node = f"project:{project_id}"
    edges: list[GraphEdge] = []
    edges.extend(
        GraphEdge(source=project_node, target=f"artifact:{artifact.step_number}", edge_type="contains", label="Snowflake")
        for artifact in artifacts
    )
    edges.extend(
        GraphEdge(source=project_node, target=f"canon:{entity.id}", edge_type="contains", label=entity.entity_type)
        for entity in canon_entities
    )
    edges.extend(
        GraphEdge(source=project_node, target=f"scene:{scene.id}", edge_type="contains", label="Scene contract")
        for scene in scenes
    )
    edges.extend(
        GraphEdge(source=project_node, target=f"memory:{record.id}", edge_type="contains", label=record.record_type)
        for record in memory_records
    )
    edges.extend(
        GraphEdge(source=f"scene:{scene.id}", target=f"artifact:{scene.source_artifact_step}", edge_type="depends_on", label="source artifact")
        for scene in scenes
        if any(artifact.step_number == scene.source_artifact_step for artifact in artifacts)
    )
    edges.extend(build_canon_reference_edges(canon_entities, scenes))
    edges.extend(build_memory_edges(memory_records, scenes, artifacts))
    return dedupe_edges(edges)


def build_canon_reference_edges(
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
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
    return edges


def build_memory_edges(
    memory_records: list[MemoryRecord],
    scenes: list[SceneContract],
    artifacts: list[SnowflakeArtifact],
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for record in memory_records:
        source_ref = record.source_ref.strip().lower()
        if not source_ref:
            continue
        for scene in scenes:
            if source_ref in scene.id.lower() or source_ref in scene.title.lower():
                edges.append(GraphEdge(source=f"memory:{record.id}", target=f"scene:{scene.id}", edge_type="informs", label="source ref"))
        for artifact in artifacts:
            artifact_ref = f"step {artifact.step_number}"
            if source_ref == artifact.artifact.lower() or source_ref == artifact_ref:
                edges.append(GraphEdge(source=f"memory:{record.id}", target=f"artifact:{artifact.step_number}", edge_type="informs", label="source ref"))
    return edges


def build_risks(
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
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
        risks.extend(scene_field_risks(scene))
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
    return risks


def scene_field_risks(scene: SceneContract) -> list[GraphRisk]:
    required_fields = [
        ("pov", "POV"),
        ("goal", "goal"),
        ("conflict", "conflict"),
        ("turning_point", "turning point"),
    ]
    risks: list[GraphRisk] = []
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
    return risks


def searchable_scene_text(scene: SceneContract) -> str:
    return " ".join(
        [
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


def truncate(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3]}..."
