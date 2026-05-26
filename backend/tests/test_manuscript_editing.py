from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.models import (
    ManuscriptProposalCreate,
    ManuscriptSceneUpdate,
    ProjectCreate,
    SceneContractCreate,
)


class ManuscriptEditingTests(unittest.TestCase):
    def test_editing_accepted_scene_creates_new_revision(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Edit Smoke",
                    premise="Test manuscript editing.",
                )
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=1,
                    title="Opening Draft",
                    pov="Mira",
                    goal="Find the missing key.",
                    conflict="The archive doors are sealed.",
                    turning_point="The map answers back.",
                    required_canon="Mira is the POV.",
                    forbidden_facts="",
                    open_threads="Who changed the map?",
                    source_artifact_step=8,
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="1. Opening Draft",
                    content="# Opening Draft\n\nMira tests the door.",
                    context="test context",
                    checklist=["reviewed"],
                ),
            )

            accepted = store.accept_manuscript_proposal(project.id, proposal.id)
            updated = store.update_manuscript_scene(
                project.id,
                scene.id,
                ManuscriptSceneUpdate(
                    title="Opening Draft Revised",
                    content="# Opening Draft Revised\n\nMira tests the sealed doors again.",
                ),
            )
            revisions = store.list_manuscript_revisions(project.id)

        self.assertIsNotNone(accepted)
        self.assertIsNotNone(updated)
        self.assertEqual(accepted.version, 1)
        self.assertEqual(updated.version, 2)
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0].title, "Opening Draft Revised")

    def test_editing_missing_scene_returns_none(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Missing Scene",
                    premise="Test missing accepted manuscript scene.",
                )
            )
            updated = store.update_manuscript_scene(
                project.id,
                "missing-scene",
                ManuscriptSceneUpdate(
                    title="No Scene",
                    content="This should not be saved.",
                ),
            )

        self.assertIsNone(updated)


if __name__ == "__main__":
    unittest.main()
