from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.cognition.interfaces import ContextPacket
from app.data import SQLiteWritingDataStore
from app.models import (
    CanonEntityCreate,
    ProjectCreate,
    SceneContractCreate,
    StoryThreadCreate,
)
from app.narrative import NarrativeSnapshot


LEGACY_OPEN_THREAD = "LEGACY_COGNITION_OPEN_THREAD"
FUTURE_CANON_STATE = "FUTURE_COGNITION_CANON_STATE"
FUTURE_SCENE = "FUTURE_COGNITION_SCENE"
STRUCTURED_THREAD = "Structured cognition thread"


class EchoCognition:
    def __init__(self) -> None:
        self.snapshot = None

    def prepare_context(self, snapshot, scope):
        self.snapshot = snapshot
        canon_state = " | ".join(
            " / ".join(
                [
                    entity.current_state,
                    entity.last_seen,
                    entity.timeline_notes,
                ]
            )
            for entity in snapshot.canon_entities
        )
        scene_state = " | ".join(
            f"{scene.title} / {scene.open_threads}" for scene in snapshot.scenes
        )
        thread_state = " | ".join(thread.title for thread in snapshot.story_threads)
        return [
            ContextPacket(
                module="echo",
                title="Echo cognition input",
                content=(f"canon={canon_state}\nscenes={scene_state}\nthreads={thread_state}"),
            )
        ]


class SceneCognitionBoundaryTests(unittest.TestCase):
    def test_scene_cognition_receives_the_same_safe_projection_as_reference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Scene Cognition Boundary",
                    premise="Cognition adapters cannot bypass scene isolation.",
                )
            )
            target_scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=2,
                    title="Archive Door",
                    pov="Mira",
                    open_threads=LEGACY_OPEN_THREAD,
                ),
            )
            store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=3,
                    title=FUTURE_SCENE,
                    pov="Mira",
                    open_threads="future legacy thread",
                ),
            )
            store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Mira",
                    summary="Archivist protagonist.",
                    current_state=FUTURE_CANON_STATE,
                    constraints="Cannot open sealed maps without the brass key.",
                    last_seen="scene 30",
                    timeline_notes="Becomes archive keeper after the reveal.",
                ),
            )
            store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title=STRUCTURED_THREAD,
                    status="developing",
                    planted_at=1,
                    importance=4,
                ),
            )
            cognition = EchoCognition()

            snapshot = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=target_scene.id,
                data_store=store,
                cognition=cognition,
            )
            context = snapshot.render_generation_context()
            safe_projection = snapshot.as_project_snapshot()

        self.assertEqual(cognition.snapshot, safe_projection)
        self.assertEqual([scene.id for scene in cognition.snapshot.scenes], [target_scene.id])
        self.assertEqual(cognition.snapshot.scenes[0].open_threads, "")
        self.assertEqual(cognition.snapshot.canon_entities[0].current_state, "")
        self.assertEqual(cognition.snapshot.canon_entities[0].last_seen, "")
        self.assertEqual(cognition.snapshot.canon_entities[0].timeline_notes, "")
        self.assertEqual(
            [thread.title for thread in cognition.snapshot.story_threads],
            [STRUCTURED_THREAD],
        )
        self.assertIn(STRUCTURED_THREAD, context)
        self.assertNotIn(LEGACY_OPEN_THREAD, context)
        self.assertNotIn(FUTURE_CANON_STATE, context)
        self.assertNotIn(FUTURE_SCENE, context)


if __name__ == "__main__":
    unittest.main()
