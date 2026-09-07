from __future__ import annotations

import networkx as nx

from app.data.ports.reading import NarrativeGraphReader
from app.models import NarrativeRelation
from app.narrative.graph import NarrativeGraph


class NarrativeGraphProjector:
    """Deterministically project authoritative narrative relations into NetworkX."""

    def __init__(self, data_store: NarrativeGraphReader):
        self.data_store = data_store

    def project(self, project_id: str) -> NarrativeGraph:
        graph = nx.MultiDiGraph(project_id=project_id, projection="narrative_domain")
        relations = sorted(
            self.data_store.list_narrative_relations(project_id),
            key=_relation_sort_key,
        )
        for relation in relations:
            graph.add_node(relation.source, **_node_attributes(relation.source))
            graph.add_node(relation.target, **_node_attributes(relation.target))
            graph.add_edge(
                relation.source,
                relation.target,
                key=relation.id,
                id=relation.id,
                project_id=relation.project_id,
                relation=relation.relation,
                valid_from=relation.valid_from,
                valid_to=relation.valid_to,
                confidence=relation.confidence,
                source_ref=relation.source_ref,
                status=relation.status,
            )
        return NarrativeGraph(graph)


def _relation_sort_key(relation: NarrativeRelation) -> tuple[str, str, str, int, str]:
    return (
        relation.source,
        relation.target,
        relation.relation,
        relation.valid_from,
        relation.id,
    )


def _node_attributes(node_id: str) -> dict[str, str]:
    node_type, separator, label = node_id.partition(":")
    if not separator:
        return {"node_type": "unknown", "label": node_id}
    return {"node_type": node_type, "label": label or node_id}
