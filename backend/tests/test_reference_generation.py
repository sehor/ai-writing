from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.agents.reference_workflow import (
    build_local_reference_suggestion,
    build_reference_context,
    scope_for_request,
)
from app.cognition.registry import CognitionRegistry
from app.cognition.snapshots import build_project_snapshot
from app.data import SQLiteWritingDataStore
from app.models import (
    CanonEntityCreate,
    MemoryRecordCreate,
    ProjectCreate,
    ReferenceGenerationRequest,
    SceneContractCreate,
    SnowflakeArtifactRevisionCreate,
    StoryThreadCreate,
)


class ReferenceGenerationTests(unittest.TestCase):
    def test_local_reference_generation_is_persisted_without_committing_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Reference Smoke",
                    premise="A cartographer must map a city that erases memory.",
                )
            )
            revision = store.create_snowflake_revision(
                project.id,
                SnowflakeArtifactRevisionCreate(
                    step_number=8,
                    content="Scene 1 asks Mira to enter the archive.",
                ),
            )
            store.decide_snowflake_revision(
                project_id=project.id,
                revision_id=revision.id,
                decision="accepted",
                expected_head_revision_id="",
            )
            store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Mira",
                    summary="A cartographer under suspicion.",
                    current_state="Outside the archive.",
                    constraints="Mira cannot know who altered the city map yet.",
                    last_seen="scene_001",
                    timeline_notes="Reached the archive before midnight.",
                ),
            )
            store.create_memory_record(
                project.id,
                MemoryRecordCreate(
                    record_type="style_rule",
                    title="Tense archive prose",
                    scope="archive scenes",
                    content="Keep sentences clipped when the map changes.",
                    tags="archive, tension",
                    source_ref="step 8",
                ),
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=1,
                    title="Archive Threshold",
                    pov="Mira",
                    goal="Enter the archive.",
                    conflict="The door rejects her map.",
                    turning_point="The map redraws the hallway.",
                    required_canon="Mira cannot know who altered the city map yet.",
                    forbidden_facts="The patron's identity.",
                    open_threads="Who changed the map?",
                    source_artifact_step=8,
                ),
            )
            store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title="Structured archive mystery",
                    status="developing",
                ),
            )
            request = ReferenceGenerationRequest(
                suggestion_type="scene_bridge",
                scope_type="scene",
                scope_ref=scene.id,
                author_problem="I do not know how to bridge into the archive scene.",
                desired_output="Three possible next moves.",
            )
            cognition = CognitionRegistry(Path(temp_dir) / "modules")
            snapshot = build_project_snapshot(project.id, store)
            packets = cognition.prepare_context(snapshot, scope_for_request(request))
            context = build_reference_context(snapshot, request, packets)
            created = store.create_reference_suggestion(
                project.id,
                build_local_reference_suggestion(request, context, snapshot, packets),
            )
            stored = store.list_reference_suggestions(project.id)
            accepted = store.update_reference_suggestion_status(
                project.id,
                created.id,
                "accepted",
            )

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].status, "pending_review")
        self.assertEqual(accepted.status, "accepted")
        self.assertIn("Scene Bridge", created.title)
        self.assertIn("I do not know how to bridge", created.used_context)
        self.assertIn("Mira cannot know", created.used_context)
        self.assertIn("Structured archive mystery", created.used_context)
        self.assertNotIn("Who changed the map?", created.used_context)
        self.assertTrue(created.workflow_trace)
        self.assertTrue(created.canon_warnings)
        self.assertEqual(created.proposed_writebacks, [])


if __name__ == "__main__":
    unittest.main()
