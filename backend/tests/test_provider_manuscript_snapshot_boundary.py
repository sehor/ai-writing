from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.llm import FakeModelGateway, ModelGatewayRegistry
from app.models import (
    CanonEntityCreate,
    KnowledgeStateCreate,
    ProjectCreate,
    SceneContractCreate,
    StoryFactCreate,
    StoryThreadCreate,
)
from app.narrative import NarrativeSnapshot
from app.services.manuscript_service import ManuscriptService


LEGACY_OPEN_THREAD = "LEGACY_PROVIDER_OPEN_THREAD"
FUTURE_SCENE = "FUTURE_PROVIDER_SCENE"
FUTURE_CANON_STATE = "FUTURE_PROVIDER_CANON_STATE"
SAFE_FACT = "SAFE_PROVIDER_FACT"
READER_ONLY_FACT = "READER_ONLY_PROVIDER_FACT"
FUTURE_FACT = "FUTURE_PROVIDER_FACT"
STRUCTURED_THREAD = "Structured provider thread"


class ProviderManuscriptSnapshotBoundaryTests(unittest.TestCase):
    def test_provider_manuscript_generation_reuses_scene_safe_snapshot_boundary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Provider Snapshot Boundary",
                    premise="Provider prose must not bypass scene-safe narrative context.",
                )
            )
            target_scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=2,
                    title="Archive Door",
                    pov="Mira",
                    goal="Open the archive.",
                    conflict="The lock changes shape.",
                    turning_point="The brass key fits.",
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
                    constraints="Keep the archive key visible.",
                    last_seen="scene 30",
                    timeline_notes="Becomes archive keeper after the reveal.",
                ),
            )

            safe_fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="brass key",
                    predicate="opens",
                    value=SAFE_FACT,
                    valid_from_scene=1,
                    reader_visible_from=1,
                ),
            )
            reader_only_fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="patron",
                    predicate="identity",
                    value=READER_ONLY_FACT,
                    valid_from_scene=1,
                    reader_visible_from=1,
                ),
            )
            future_fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="archive",
                    predicate="keeper",
                    value=FUTURE_FACT,
                    valid_from_scene=3,
                    reader_visible_from=3,
                ),
            )
            for fact, known_from in [
                (safe_fact, 1),
                (reader_only_fact, 3),
                (future_fact, 3),
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

            expected_context = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=target_scene.id,
                data_store=store,
            ).render_generation_context()
            gateway = FakeModelGateway(["PROVIDER_BOUNDARY_DRAFT"])
            registry = ModelGatewayRegistry()
            registry.register("deepseek", lambda: gateway)
            service = ManuscriptService(data_store=store, cognition=None)
            service.gateway_registry = registry

            proposal = service.generate_provider_proposal(project.id, target_scene.id)
            manuscript_scenes = store.list_manuscript_scenes(project.id)

        self.assertEqual(len(gateway.requests), 1)
        prompt_context = gateway.requests[0].prompt.messages[1].content
        self.assertIn(expected_context, prompt_context)
        self.assertEqual(proposal.context, expected_context)
        self.assertEqual(proposal.status, "pending_review")
        self.assertIn(SAFE_FACT, prompt_context)
        self.assertIn(STRUCTURED_THREAD, prompt_context)
        self.assertNotIn(LEGACY_OPEN_THREAD, prompt_context)
        self.assertNotIn(READER_ONLY_FACT, prompt_context)
        self.assertNotIn(FUTURE_FACT, prompt_context)
        self.assertNotIn(FUTURE_CANON_STATE, prompt_context)
        self.assertNotIn(FUTURE_SCENE, prompt_context)
        self.assertEqual(manuscript_scenes, [])


if __name__ == "__main__":
    unittest.main()
