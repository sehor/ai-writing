from __future__ import annotations

from collections.abc import Iterable

import networkx as nx


class NarrativeGraph:
    """Read/query wrapper around a derived directed multi-relation graph."""

    def __init__(self, graph: nx.MultiDiGraph):
        if not isinstance(graph, nx.MultiDiGraph):
            raise TypeError("NarrativeGraph requires a networkx.MultiDiGraph")
        self._graph = graph

    @property
    def networkx(self) -> nx.MultiDiGraph:
        """Expose the derived graph for analysis without implying persistence ownership."""
        return self._graph

    @property
    def graph(self) -> nx.MultiDiGraph:
        """Backward-friendly alias for callers that expect a graph property."""
        return self._graph

    def neighbors(self, node: str) -> list[str]:
        """Return deterministic one-hop neighbors in either direction."""
        if node not in self._graph:
            return []
        connected = set(self._graph.predecessors(node)) | set(self._graph.successors(node))
        return sorted(connected)

    def path(self, source: str, target: str) -> list[str]:
        """Return a deterministic shortest directed path, or an empty list if unreachable."""
        if source not in self._graph or target not in self._graph:
            return []
        try:
            paths = nx.all_shortest_paths(self._graph, source, target)
            return list(min(tuple(path) for path in paths))
        except nx.NetworkXNoPath:
            return []

    def ancestors(self, node: str) -> list[str]:
        if node not in self._graph:
            return []
        return sorted(nx.ancestors(self._graph, node))

    def descendants(self, node: str) -> list[str]:
        if node not in self._graph:
            return []
        return sorted(nx.descendants(self._graph, node))

    def affected(self, node: str) -> list[str]:
        """Reverse-traverse incoming relations to find nodes that depend on the seed."""
        if node not in self._graph:
            return []
        reverse_graph = self._graph.reverse(copy=False)
        return sorted(nx.descendants(reverse_graph, node))

    def subgraph(self, scope: str | Iterable[str]) -> "NarrativeGraph":
        """Return an induced copy for the requested node IDs."""
        requested = {scope} if isinstance(scope, str) else set(scope)
        existing = sorted(node for node in requested if node in self._graph)
        return NarrativeGraph(self._graph.subgraph(existing).copy())
