from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.cognition.registry import CognitionRegistry
from app.cognition.snapshots import build_project_snapshot
from app.data import SQLiteWritingDataStore
from app.models import (
    CanonEntityCreate,
    ProjectCreate,
    ReferenceGenerationRequest,
    SceneContractCreate,
    StoryThreadCreate,
)
from app.narrative import NarrativeSnapshot
from app.services.compile_service import build_compile_context
from app.services.reference_service import ReferenceService


LEGACY_OPEN_THREAD = "LEGACY_OPEN_THREAD_SENTINEL"
STRUCTURED_THREAD = "Structured archive thread"


class StoryThreadBoundaryTests(unittest.TestCase):
    def _create_project_with_legacy_thread(self, temp_dir: str):
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        project = store.create_project(
            ProjectCreate(
                title="Structured Threads",
                premise="Only typed story threads drive narrative lifecycle.",
            )
        )
        scene = store.create_scene_contract(
            project.id,
            SceneContractCreate(
                sequence=2,
                title="Archive Door",
                pov="Mira",
                goal="Open the archive.",
                conflict="The key is missing.",
                turning_point="A hidden latch moves.",
                open_threads=LEGACY_OPEN_THREAD,
            ),
        )
        return store, project, scene

    def test_scene_generation_context_uses_structured_threads_not_legacy_open_threads(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project, scene = self._create_project_with_legacy_thread(temp_dir)
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

            snapshot = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=scene.id,
                data_store=store,
            )
            context = snapshot.render_generation_context()
            legacy_compile_context = build_compile_context(
                project.title,
                scene,
                canon_entities=[],
                memory_records=[],
                artifacts=[],
            )

        self.assertIn(STRUCTURED_THREAD, context)
        self.assertNotIn(LEGACY_OPEN_THREAD, context)
        self.assertNotIn(LEGACY_OPEN_THREAD, legacy_compile_context)

    def test_scene_reference_context_does_not_reintroduce_legacy_open_threads(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project, scene = self._create_project_with_legacy_thread(temp_dir)
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
            service = ReferenceService(
                data_store=store,
                cognition=CognitionRegistry(Path(temp_dir) / "modules"),
            )

            suggestion = service.generate_local(
                project.id,
                ReferenceGenerationRequest(
                    scope_type="scene",
                    scope_ref=scene.id,
                    author_problem="How should this scene advance?",
                ),
            )

        self.assertIn(STRUCTURED_THREAD, suggestion.used_context)
        self.assertNotIn(LEGACY_OPEN_THREAD, suggestion.used_context)

    def test_graph_analysis_ignores_legacy_open_threads_until_structured_thread_exists(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project, _ = self._create_project_with_legacy_thread(temp_dir)
            store.create_canon_entity(
                project.id,
                CanonEntityCreate(entity_type="character", name=LEGACY_OPEN_THREAD),
            )
            graph_module = CognitionRegistry(Path(temp_dir) / "modules").graph_module

            legacy_only = graph_module.analyze(build_project_snapshot(project.id, store))
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
            structured = graph_module.analyze(build_project_snapshot(project.id, store))

        self.assertEqual(legacy_only.summary.unresolved_thread_count, 0)
        self.assertEqual(legacy_only.summary.canon_reference_count, 0)
        self.assertFalse(
            any(risk.title == "Open thread requires review" for risk in legacy_only.risks)
        )
        self.assertEqual(structured.summary.unresolved_thread_count, 1)


if __name__ == "__main__":
    unittest.main()
