from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.cognition.interfaces import ContextPacket
from app.cognition.snapshots import NarrativeSnapshot
from app.data import SQLiteWritingDataStore
from app.llm_wiki.interfaces import WikiContextQuery, WikiContextResult, WikiEvidence
from app.models import (
    CanonEntityCreate,
    ManuscriptProposalCreate,
    MemoryRecordCreate,
    ProjectCreate,
    SceneContractCreate,
    SnowflakeArtifact,
    StoryFactCreate,
)


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


if __name__ == "__main__":
    unittest.main()
