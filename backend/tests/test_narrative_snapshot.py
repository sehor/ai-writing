from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.cognition.interfaces import ContextPacket
from app.cognition.snapshots import NarrativeSnapshot as LegacyNarrativeSnapshot
from app.data import SQLiteWritingDataStore
from app.narrative import NarrativeSnapshot
from app.llm_wiki.interfaces import WikiContextQuery, WikiContextResult, WikiEvidence
from app.models import (
    CanonEntityCreate,
    KnowledgeStateCreate,
    ManuscriptProposalCreate,
    MemoryRecordCreate,
    NarrativeRelationCreate,
    ProjectCreate,
    SceneContractCreate,
    SnowflakeArtifact,
    StoryFactCreate,
    StoryThreadCreate,
    StoryThreadEventCreate,
)
from app.services.manuscript_service import ManuscriptService


class RecordingCognition:
    def __init__(self) -> None:
        self.memory_titles: list[str] = []

    def prepare_context(self, snapshot, scope):
        self.memory_titles = [record.title for record in snapshot.memory_records]
        return [
            ContextPacket(
                module="test-memory",
                title="Filtered memory",
                content=" | ".join(record.content for record in snapshot.memory_records),
            )
        ]


class UnfilteredWiki:
    def __init__(self) -> None:
        self.queries: list[WikiContextQuery] = []

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        self.queries.append(query)
        return WikiContextResult(
            summary="unfiltered fake",
            evidence=[
                WikiEvidence(
                    source_ref="revision:scene-19",
                    title="Earlier observed scene",
                    excerpt="EARLIER_OBSERVED_PROSE",
                    knowledge_class="observed",
                    snowflake_step=10,
                    scope="scene-19",
                    story_position=19,
                ),
                WikiEvidence(
                    source_ref="revision:scene-21",
                    title="Future observed scene",
                    excerpt="FUTURE_OBSERVED_PROSE",
                    knowledge_class="observed",
                    snowflake_step=10,
                    scope="scene-21",
                    story_position=21,
                ),
                WikiEvidence(
                    source_ref="snowflake:8",
                    title="Full scene plan",
                    excerpt="STEP8_FUTURE_PLAN",
                    knowledge_class="planned",
                    snowflake_step=8,
                    scope="",
                    story_position=None,
                ),
            ],
            constraints=[],
        )


class NarrativeSnapshotTests(unittest.TestCase):
    def test_legacy_cognition_import_reexports_narrative_snapshot(self) -> None:
        self.assertIs(LegacyNarrativeSnapshot, NarrativeSnapshot)

    def test_for_scene_uses_only_prior_accepted_prose_and_non_future_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Snapshot Novel",
                    premise="An archive rearranges the truth around its readers.",
                )
            )
            scene_19 = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=19, title="Hidden Key", pov="Mira"),
            )
            scene_20 = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=20,
                    title="Archive Door",
                    pov="Mira",
                    goal="Open the sealed door.",
                    forbidden_facts="Do not reveal who forged the map.",
                    source_artifact_step=8,
                ),
            )
            scene_21 = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=21, title="The Forgery", pov="Mira"),
            )
            store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Mira",
                    summary="Archivist protagonist.",
                    current_state="FUTURE_CANON_STATE: Mira becomes archive keeper in scene 30.",
                    constraints="Cannot read sealed maps without the brass key.",
                ),
            )
            hidden_fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="the archivist",
                    predicate="forged",
                    value="HIDDEN_STORY_FACT: the map",
                    valid_from_scene=1,
                    reader_visible_from=21,
                    source_ref="author:canon",
                ),
            )
            store.save_snowflake_artifact(
                SnowflakeArtifact(
                    project_id=project.id,
                    step_number=8,
                    artifact="scene_contracts",
                    content="STEP8_SECRET: scene 21 reveals the archivist forged the map.",
                )
            )

            earlier = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene_19.id,
                    title=scene_19.title,
                    content="EARLIER_ACCEPTED_PROSE: Mira hides the brass key.",
                ),
            )
            store.accept_manuscript_proposal(project.id, earlier.id)
            future = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene_21.id,
                    title=scene_21.title,
                    content="FUTURE_ACCEPTED_PROSE: the archivist forged the map.",
                ),
            )
            store.accept_manuscript_proposal(project.id, future.id)

            store.create_memory_record(
                project.id,
                MemoryRecordCreate(
                    record_type="prose_sample",
                    title="Earlier prose sample",
                    scope=scene_19.id,
                    content="EARLIER_PROSE_SAMPLE",
                    source_ref="revision:scene-19",
                ),
            )
            store.create_memory_record(
                project.id,
                MemoryRecordCreate(
                    record_type="prose_sample",
                    title="Future prose sample",
                    scope=scene_21.id,
                    content="FUTURE_PROSE_SAMPLE",
                    source_ref="revision:scene-21",
                ),
            )
            store.create_memory_record(
                project.id,
                MemoryRecordCreate(
                    record_type="style_rule",
                    title="Global style rule",
                    content="Keep dialogue clipped and concrete.",
                ),
            )

            cognition = RecordingCognition()
            wiki = UnfilteredWiki()
            snapshot = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=scene_20.id,
                data_store=store,
                cognition=cognition,
                llm_wiki=wiki,
            )
            context = snapshot.render_generation_context()

            self.assertEqual(snapshot.scene.id, scene_20.id)
            self.assertIn(hidden_fact.id, {fact.id for fact in snapshot.world_truth})
            self.assertEqual(
                [scene.scene_id for scene in snapshot.manuscript_scenes],
                [scene_19.id],
            )
            self.assertIn("Earlier prose sample", cognition.memory_titles)
            self.assertIn("Global style rule", cognition.memory_titles)
            self.assertNotIn("Future prose sample", cognition.memory_titles)
            self.assertEqual(wiki.queries[-1].story_position, 20)
            self.assertEqual(wiki.queries[-1].spoiler_horizon, 20)
            self.assertEqual(wiki.queries[-1].scope, "")

            self.assertIn("EARLIER_ACCEPTED_PROSE", context)
            self.assertIn("EARLIER_OBSERVED_PROSE", context)
            self.assertIn("EARLIER_PROSE_SAMPLE", context)
            self.assertIn("Do not reveal who forged the map.", context)
            self.assertNotIn("FUTURE_ACCEPTED_PROSE", context)
            self.assertNotIn("FUTURE_OBSERVED_PROSE", context)
            self.assertNotIn("FUTURE_PROSE_SAMPLE", context)
            self.assertNotIn("STEP8_FUTURE_PLAN", context)
            self.assertNotIn("STEP8_SECRET", context)
            self.assertNotIn("FUTURE_CANON_STATE", context)
            self.assertNotIn("HIDDEN_STORY_FACT", context)
            self.assertIn("Protected world facts withheld from prose context: 1", context)
            self.assertIn("Cannot read sealed maps without the brass key.", context)

    def test_for_scene_rebuilds_temporal_knowledge_graph_and_thread_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = SQLiteWritingDataStore(root / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Snapshot Isolation",
                    premise="Truth, knowledge, and relationships move on different clocks.",
                )
            )
            scene_1 = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=1, title="First Trace", pov="Mira"),
            )
            scene_2 = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=2, title="Second Trace", pov="Mira"),
            )
            scene_3 = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=3,
                    title="Archive Search",
                    pov="Mira",
                    forbidden_facts="Do not reveal the map forger.",
                ),
            )
            scene_4 = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=4, title="The Reveal", pov="Mira"),
            )

            shared = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="archive door",
                    predicate="requires",
                    value="SHARED_SAFE_KEY",
                    valid_from_scene=1,
                    reader_visible_from=1,
                ),
            )
            reader_only = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="old map",
                    predicate="contains",
                    value="READER_ONLY_VALUE",
                    valid_from_scene=1,
                    reader_visible_from=1,
                ),
            )
            pov_only = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="Mira",
                    predicate="remembers",
                    value="POV_ONLY_VALUE",
                    valid_from_scene=1,
                    reader_visible_from=4,
                ),
            )
            expired = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="Mira",
                    predicate="location",
                    value="EXPIRED_HARBOR_VALUE",
                    valid_from_scene=1,
                    valid_to_scene=2,
                    reader_visible_from=1,
                ),
            )
            future = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="map forger",
                    predicate="identity",
                    value="FUTURE_FACT_VALUE",
                    valid_from_scene=4,
                    reader_visible_from=4,
                ),
            )
            related_only = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="Chen",
                    predicate="recognizes",
                    value="RELATED_CHARACTER_ONLY_VALUE",
                    valid_from_scene=1,
                    reader_visible_from=4,
                ),
            )
            for fact, known_from in [
                (shared, 1),
                (reader_only, 4),
                (pov_only, 1),
                (expired, 1),
                (future, 4),
            ]:
                store.set_knowledge_state(
                    project.id,
                    fact.id,
                    KnowledgeStateCreate(
                        scope="character_knowledge",
                        character="Mira",
                        known_from_scene=known_from,
                    ),
                )
            store.set_knowledge_state(
                project.id,
                related_only.id,
                KnowledgeStateCreate(
                    scope="character_knowledge",
                    character="Chen",
                    known_from_scene=1,
                ),
            )

            active_relation = store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="location:archive",
                    relation="AT",
                    valid_from=1,
                    source_ref="scene:1",
                ),
            )
            related_relation = store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="character:chen",
                    relation="TRUSTS",
                    valid_from=1,
                    source_ref="scene:1",
                ),
            )
            expired_relation = store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="location:harbor",
                    relation="AT",
                    valid_from=1,
                    valid_to=2,
                    source_ref="scene:1",
                ),
            )
            future_relation = store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source="character:mira",
                    target="secret:map-forger",
                    relation="KNOWS",
                    valid_from=4,
                    source_ref="scene:4",
                ),
            )

            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title="Who forged the map?",
                    target_payoff_from=4,
                    target_payoff_to=6,
                    importance=5,
                    reveal_constraints="Do not name the forger before payoff.",
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scene_1.id,
                    action="plant",
                    note="MAP_SIGNATURE_DIFFERS",
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scene_2.id,
                    action="reinforce",
                    note="INK_MATCHES",
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scene_4.id,
                    action="payoff",
                    note="FUTURE_PAYOFF_NOTE",
                ),
            )
            self.assertEqual(store.list_story_threads(project.id)[0].status, "paid_off")

            snapshot = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=scene_3.id,
                data_store=store,
            )
            rebuilt = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=scene_3.id,
                data_store=store,
            )
            context = snapshot.render_generation_context()

            self.assertEqual(snapshot, rebuilt)
            self.assertEqual(snapshot.scene, scene_3)
            self.assertEqual(
                {fact.id for fact in snapshot.world_truth},
                {shared.id, reader_only.id, pov_only.id, related_only.id},
            )
            self.assertEqual(
                {fact.id for fact in snapshot.reader_knowledge},
                {shared.id, reader_only.id},
            )
            self.assertEqual(
                {fact.id for fact in snapshot.pov_knowledge},
                {shared.id, pov_only.id},
            )
            self.assertNotIn(expired.id, {fact.id for fact in snapshot.world_truth})
            self.assertNotIn(future.id, {fact.id for fact in snapshot.world_truth})
            self.assertIn(future.id, snapshot.future_fact_ids)
            self.assertEqual(
                {fact.id for fact in snapshot.related_character_knowledge["chen"]},
                {related_only.id},
            )

            self.assertEqual(
                {relation.id for relation in snapshot.narrative_relations},
                {active_relation.id, related_relation.id},
            )
            self.assertNotIn(
                expired_relation.id,
                {relation.id for relation in snapshot.narrative_relations},
            )
            self.assertIn(future_relation.id, snapshot.future_relation_ids)

            self.assertEqual([item.id for item in snapshot.active_threads], [thread.id])
            self.assertEqual(snapshot.active_threads[0].status, "developing")
            self.assertEqual(
                [event.action for event in snapshot.story_thread_events],
                ["plant", "reinforce"],
            )
            self.assertTrue(
                any(
                    "Do not reveal the map forger." in item
                    for item in snapshot.safe_future_constraints
                )
            )
            self.assertTrue(
                any(
                    "Do not name the forger before payoff." in item
                    for item in snapshot.safe_future_constraints
                )
            )

            self.assertIn("SHARED_SAFE_KEY", context)
            self.assertEqual(
                [event.note for event in snapshot.story_thread_events],
                ["MAP_SIGNATURE_DIFFERS", "INK_MATCHES"],
            )
            self.assertNotIn("MAP_SIGNATURE_DIFFERS", context)
            self.assertNotIn("INK_MATCHES", context)
            self.assertNotIn("READER_ONLY_VALUE", context)
            self.assertNotIn("POV_ONLY_VALUE", context)
            self.assertNotIn("EXPIRED_HARBOR_VALUE", context)
            self.assertNotIn("FUTURE_FACT_VALUE", context)
            self.assertNotIn("RELATED_CHARACTER_ONLY_VALUE", context)
            self.assertNotIn("FUTURE_PAYOFF_NOTE", context)
            self.assertNotIn("secret:map-forger", context)
            self.assertIn("Reader-only facts withheld from POV context: 1", context)
            self.assertIn("POV-only facts withheld from reader context: 1", context)
            self.assertIn("Future story facts withheld from generation: 1", context)
            self.assertIn("Future narrative relations withheld from generation: 1", context)

            derived_files = [
                path
                for path in root.rglob("*")
                if path.is_file()
                and ("snapshot" in path.name.lower() or "graph" in path.name.lower())
            ]
            self.assertEqual(derived_files, [])

    def test_manuscript_generation_uses_snapshot_without_bypassing_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Snapshot Review",
                    premise="Generation remains a proposal until the author accepts it.",
                )
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=2,
                    title="Review Gate",
                    pov="Mira",
                    goal="Open the archive door.",
                    conflict="The lock changes shape.",
                    turning_point="The brass key fits.",
                ),
            )
            safe = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="brass key",
                    predicate="opens",
                    value="SAFE_GENERATION_VALUE",
                    valid_from_scene=1,
                    reader_visible_from=1,
                ),
            )
            hidden = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="patron",
                    predicate="identity",
                    value="HIDDEN_GENERATION_VALUE",
                    valid_from_scene=1,
                    reader_visible_from=3,
                ),
            )
            future = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="archive",
                    predicate="keeper",
                    value="FUTURE_GENERATION_VALUE",
                    valid_from_scene=3,
                    reader_visible_from=3,
                ),
            )
            for fact, known_from in [(safe, 1), (hidden, 3), (future, 3)]:
                store.set_knowledge_state(
                    project.id,
                    fact.id,
                    KnowledgeStateCreate(
                        scope="character_knowledge",
                        character="Mira",
                        known_from_scene=known_from,
                    ),
                )

            expected_context = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=scene.id,
                data_store=store,
            ).render_generation_context()
            service = ManuscriptService(data_store=store, llm_wiki=None, cognition=None)
            proposal = service.generate_local_proposal(project.id, scene.id)

            self.assertEqual(proposal.context, expected_context)
            self.assertEqual(proposal.status, "pending_review")
            self.assertIn("SAFE_GENERATION_VALUE", proposal.context)
            self.assertNotIn("HIDDEN_GENERATION_VALUE", proposal.context)
            self.assertNotIn("FUTURE_GENERATION_VALUE", proposal.context)
            self.assertEqual(store.list_manuscript_scenes(project.id), [])

            accepted = service.update_proposal_status(project.id, proposal.id, "accepted")
            self.assertEqual(accepted.status, "accepted")
            self.assertEqual(len(store.list_manuscript_scenes(project.id)), 1)


if __name__ == "__main__":
    unittest.main()
