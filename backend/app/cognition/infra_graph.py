from pathlib import Path

from app.cognition.interfaces import ProjectCognitionSnapshot
from app.models import (
    GraphAnalysisResponse,
    GraphAnalysisSummary,
)
from app.cognition.graph_core import build_graph_nodes, build_graph_edges, build_graph_risks


class LocalInfraGraphModule:
    name = "infra_graph"

    def __init__(self, modules_root: Path):
        self.modules_root = modules_root

    def project_path(self, project_id: str) -> Path:
        return self.modules_root / project_id / "modules" / self.name

    def analyze(self, snapshot: ProjectCognitionSnapshot) -> GraphAnalysisResponse:
        nodes = build_graph_nodes(
            snapshot.project.id,
            snapshot.project.title,
            snapshot.artifacts,
            snapshot.canon_entities,
            snapshot.scenes,
            snapshot.memory_records,
            snapshot.story_threads,
        )
        edges = build_graph_edges(
            snapshot.project.id,
            snapshot.artifacts,
            snapshot.canon_entities,
            snapshot.scenes,
            snapshot.memory_records,
            snapshot.story_threads,
            snapshot.story_thread_events,
        )
        risks = build_graph_risks(
            snapshot.artifacts,
            snapshot.canon_entities,
            snapshot.scenes,
            snapshot.memory_records,
            snapshot.story_threads,
            snapshot.story_thread_events,
        )
        summary = GraphAnalysisSummary(
            node_count=len(nodes),
            edge_count=len(edges),
            risk_count=len(risks),
            critical_count=sum(1 for risk in risks if risk.severity == "critical"),
            warning_count=sum(1 for risk in risks if risk.severity == "warning"),
            unresolved_thread_count=(
                sum(
                    1
                    for thread in snapshot.story_threads
                    if thread.status not in {"paid_off", "abandoned"}
                )
                if snapshot.story_threads
                else sum(1 for scene in snapshot.scenes if scene.open_threads)
            ),
            canon_reference_count=sum(
                1
                for edge in edges
                if edge.edge_type == "references" and edge.target.startswith("canon:")
            ),
        )
        return GraphAnalysisResponse(
            project_id=snapshot.project.id,
            summary=summary,
            nodes=nodes,
            edges=edges,
            risks=risks,
        )
