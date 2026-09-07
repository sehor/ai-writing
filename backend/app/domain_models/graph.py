from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GraphNodeType = Literal[
    "project",
    "snowflake_artifact",
    "canon_entity",
    "scene",
    "memory_record",
    "story_thread",
]


GraphEdgeType = Literal["contains", "depends_on", "references", "informs"]


GraphRiskSeverity = Literal["info", "warning", "critical"]


class GraphAnalysisSummary(BaseModel):
    node_count: int
    edge_count: int
    risk_count: int
    critical_count: int
    warning_count: int
    unresolved_thread_count: int
    canon_reference_count: int


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: GraphNodeType
    status: str = ""


class GraphEdge(BaseModel):
    source: str
    target: str
    edge_type: GraphEdgeType
    label: str = ""


class GraphRisk(BaseModel):
    id: str
    severity: GraphRiskSeverity
    title: str
    detail: str
    source_id: str = ""


class GraphAnalysisResponse(BaseModel):
    project_id: str
    summary: GraphAnalysisSummary
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    risks: list[GraphRisk] = Field(default_factory=list)
