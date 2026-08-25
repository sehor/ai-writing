from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.models import (
    ManuscriptChapterCreate,
    ManuscriptProposalCreate,
    ProjectCreate,
    SceneContractCreate,
)
from app.manuscript_export import build_export_markdown


class ManuscriptChapterTests(unittest.TestCase):
    def test_scene_contracts_can_be_grouped_under_ordered_chapters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Chapter Smoke",
                    premise="Test chapter-level manuscript organization.",
                )
            )
            second = store.create_manuscript_chapter(
                project.id,
                ManuscriptChapterCreate(
                    sequence=2,
                    title="The Archive Answers",
                    summary="Mira learns the archive has a voice.",
                ),
            )
            first = store.create_manuscript_chapter(
                project.id,
                ManuscriptChapterCreate(
                    sequence=1,
                    title="The Locked Map",
                    summary="Mira reaches the sealed archive.",
                ),
            )
            store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    chapter_id=first.id,
                    sequence=1,
                    title="Archive Threshold",
                    pov="Mira",
                    goal="Enter the archive.",
                    conflict="The map refuses the door.",
                    turning_point="The map redraws itself.",
                    required_canon="Mira has the altered map.",
                    forbidden_facts="The patron's identity.",
                    open_threads="Who changed the map?",
                    source_artifact_step=8,
                ),
            )
            chapters = store.list_manuscript_chapters(project.id)
            scenes = store.list_scene_contracts(project.id)

        self.assertEqual([chapter.id for chapter in chapters], [first.id, second.id])
        self.assertEqual(scenes[0].chapter_id, first.id)

    def test_export_groups_accepted_scenes_by_chapter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Grouped Export",
                    premise="Test chapter headings in manuscript export.",
                )
            )
            chapter = store.create_manuscript_chapter(
                project.id,
                ManuscriptChapterCreate(
                    sequence=1,
                    title="The Locked Map",
                    summary="Mira reaches the sealed archive.",
                ),
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    chapter_id=chapter.id,
                    sequence=1,
                    title="Archive Threshold",
                    pov="Mira",
                    goal="Enter the archive.",
                    conflict="The map refuses the door.",
                    turning_point="The map redraws itself.",
                    required_canon="Mira has the altered map.",
                    forbidden_facts="The patron's identity.",
                    open_threads="Who changed the map?",
                    source_artifact_step=8,
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="Archive Threshold",
                    content="Mira pressed the map to the sealed door.",
                    context="test context",
                    checklist=["reviewed"],
                ),
            )
            accepted = store.accept_manuscript_proposal(project.id, proposal.id)

            export = build_export_markdown(
                project.title,
                [chapter],
                [(accepted, scene)],
            )

        self.assertIn("# Grouped Export", export)
        self.assertIn("## Chapter 1: The Locked Map", export)
        self.assertIn("### Archive Threshold", export)
        self.assertIn("Mira pressed the map", export)


if __name__ == "__main__":
    unittest.main()
