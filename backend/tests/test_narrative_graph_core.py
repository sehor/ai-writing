from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import networkx as nx

from app.data import SQLiteWritingDataStore
from app.models import NarrativeRelationCreate, ProjectCreate
from app.narrative import NarrativeGraphProjector


class NarrativeGraphCoreTests(unittest.TestCase):
    def _create_store(self, temp_dir: str) -> tuple[SQLiteWritingDataStore, str]:
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        project = store.create_project(
            ProjectCreate(title="Narrative Graph", premise="Relationships form a directed graph.")
        )
        return store, project.id

    def test_projection_uses_multidigraph_and_preserves_relation_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id = self._create_store(temp_dir)
            suspects = store.create_narrative_relation(
                project_id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="character:chen",
                    relation="SUSPECTS",
                    valid_from=32,
                    valid_to=40,
                    confidence=0.72,
                    source_ref="revision:scene-32:v2",
                    status="confirmed",
                ),
            )
            owes = store.create_narrative_relation(
                project_id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="character:chen",
                    relation="OWES",
                    valid_from=12,
                    confidence=0.91,
                    source_ref="canon:debt",
                    status="planned",
                ),
            )

            graph = NarrativeGraphProjector(store).project(project_id)

            self.assertIsInstance(graph.networkx, nx.MultiDiGraph)
            self.assertEqual(graph.networkx.number_of_nodes(), 2)
            self.assertEqual(graph.networkx.number_of_edges(), 2)
            self.assertEqual(
                set(graph.networkx["character:mira"]["character:chen"]), {suspects.id, owes.id}
            )

            edge = graph.networkx["character:mira"]["character:chen"][suspects.id]
            self.assertEqual(edge["relation"], "SUSPECTS")
            self.assertEqual(edge["valid_from"], 32)
            self.assertEqual(edge["valid_to"], 40)
            self.assertEqual(edge["confidence"], 0.72)
            self.assertEqual(edge["source_ref"], "revision:scene-32:v2")
            self.assertEqual(edge["status"], "confirmed")
            self.assertEqual(graph.path("character:chen", "character:mira"), [])

    def test_traversal_api_respects_direction_and_reverse_affected_semantics(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id = self._create_store(temp_dir)
            for source, target, relation in [
                ("event:a", "event:b", "CAUSES"),
                ("event:c", "event:b", "ENABLES"),
                ("event:b", "event:d", "CAUSES"),
                ("event:d", "event:e", "CAUSES"),
            ]:
                store.create_narrative_relation(
                    project_id,
                    NarrativeRelationCreate(
                        source=source,
                        target=target,
                        relation=relation,
                        valid_from=1,
                    ),
                )

            graph = NarrativeGraphProjector(store).project(project_id)

            self.assertEqual(graph.neighbors("event:b"), ["event:a", "event:c", "event:d"])
            self.assertEqual(
                graph.path("event:a", "event:e"), ["event:a", "event:b", "event:d", "event:e"]
            )
            self.assertEqual(graph.ancestors("event:d"), ["event:a", "event:b", "event:c"])
            self.assertEqual(graph.descendants("event:b"), ["event:d", "event:e"])
            self.assertEqual(graph.affected("event:b"), ["event:a", "event:c"])

            scoped = graph.subgraph({"event:b", "event:d", "event:e"})
            self.assertEqual(sorted(scoped.networkx.nodes), ["event:b", "event:d", "event:e"])
            self.assertEqual(
                list(scoped.networkx.edges(keys=False)),
                [("event:b", "event:d"), ("event:d", "event:e")],
            )

    def test_graph_can_be_fully_rebuilt_from_sqlite_domain(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id = self._create_store(temp_dir)
            first = store.create_narrative_relation(
                project_id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="secret:map",
                    relation="KNOWS",
                    valid_from=20,
                    confidence=1.0,
                    source_ref="scene:20",
                ),
            )

            original = NarrativeGraphProjector(store).project(project_id)
            original_edges = list(original.networkx.edges(keys=True, data=True))
            self.assertEqual(original_edges[0][2], first.id)

            original.networkx.add_edge("ghost:a", "ghost:b", key="derived-only", relation="BROKEN")
            rebuilt = NarrativeGraphProjector(store).project(project_id)

            self.assertNotIn("ghost:a", rebuilt.networkx)
            self.assertEqual(list(rebuilt.networkx.edges(keys=True, data=True)), original_edges)

            second = store.create_narrative_relation(
                project_id,
                NarrativeRelationCreate(
                    source="secret:map",
                    target="event:reveal",
                    relation="TRIGGERS",
                    valid_from=80,
                    source_ref="scene:80",
                ),
            )
            rebuilt_again = NarrativeGraphProjector(store).project(project_id)
            self.assertEqual(rebuilt.networkx.number_of_edges(), 1)
            self.assertEqual(rebuilt_again.networkx.number_of_edges(), 2)
            self.assertIn(second.id, rebuilt_again.networkx["secret:map"]["event:reveal"])


if __name__ == "__main__":
    unittest.main()
