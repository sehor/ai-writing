from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.models import (
    KnowledgeStateCreate,
    NarrativeRelationCreate,
    ProjectCreate,
    StoryFactCreate,
)


class NarrativeDomainPhase0Tests(unittest.TestCase):
    def test_story_fact_projects_world_and_reader_knowledge_states(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(title="Knowledge", premise="A secret exists before it is revealed.")
            )

            fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="the sealed letter",
                    predicate="author",
                    value="the queen",
                    valid_from_scene=1,
                    reader_visible_from=80,
                    source_ref="canon:letter-author",
                ),
            )

            states = store.list_knowledge_states(project.id, fact.id)
            by_scope = {state.scope: state for state in states}
            self.assertEqual(by_scope["world_truth"].known_from_scene, 1)
            self.assertEqual(by_scope["reader_knowledge"].known_from_scene, 80)
            self.assertEqual(by_scope["world_truth"].source_ref, "canon:letter-author")

    def test_character_knowledge_state_can_reveal_a_fact_later_than_the_reader(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(title="Character knowledge", premise="Characters learn at different times.")
            )
            fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="the sealed letter",
                    predicate="author",
                    value="the queen",
                    valid_from_scene=1,
                    reader_visible_from=80,
                ),
            )

            state = store.set_knowledge_state(
                project.id,
                fact.id,
                KnowledgeStateCreate(
                    scope="character_knowledge",
                    character="Mira",
                    known_from_scene=84,
                    source_ref="scene:84",
                ),
            )

            self.assertEqual(state.fact_id, fact.id)
            self.assertEqual(state.character, "Mira")
            self.assertEqual(store.list_character_facts_at(project.id, "Mira", 83), [])
            self.assertEqual(
                [item.id for item in store.list_character_facts_at(project.id, "mira", 84)],
                [fact.id],
            )
            self.assertEqual([item.id for item in store.list_reader_facts_at(project.id, 80)], [fact.id])

    def test_narrative_relation_persists_temporal_and_provenance_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(title="Relations", premise="Relationships change over time.")
            )

            relation = store.create_narrative_relation(
                project.id,
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

            self.assertEqual(relation.relation, "SUSPECTS")
            self.assertEqual(relation.confidence, 0.72)
            self.assertEqual(relation.source_ref, "revision:scene-32:v2")
            self.assertEqual(store.list_narrative_relations_at(project.id, 31), [])
            self.assertEqual(
                [item.id for item in store.list_narrative_relations_at(project.id, 32)],
                [relation.id],
            )
            self.assertEqual(
                [item.id for item in store.list_narrative_relations_at(project.id, 40)],
                [relation.id],
            )
            self.assertEqual(store.list_narrative_relations_at(project.id, 41), [])

    def test_narrative_relation_rejects_an_inverted_validity_interval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(title="Invalid relation", premise="Intervals must be ordered.")
            )

            with self.assertRaisesRegex(ValueError, "valid_to cannot be before valid_from"):
                store.create_narrative_relation(
                    project.id,
                    NarrativeRelationCreate(
                        source="character:mira",
                        target="character:chen",
                        relation="TRUSTS",
                        valid_from=10,
                        valid_to=9,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
