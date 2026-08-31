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

# P1-01: every committed revision must schedule exactly this job set.
REVISION_JOB_TYPES = [
    "clp_extraction",
    "consistency_analysis",
    "llm_wiki_ingest",
    "writeback_analysis",
]


class ManuscriptEditingTests(unittest.TestCase):
    def _seed_accepted_scene(self, temp_dir: str) -> tuple[SQLiteWritingDataStore, str, str]:
        """Create a project with one accepted scene; return store/project/scene ids."""
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        project = store.create_project(
            ProjectCreate(
                title="Pipeline Smoke",
                premise="Every committed revision enters the same pipeline.",
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
        self.assertIsNotNone(accepted)
        return store, project.id, scene.id

    def _job_types_for_revision(
        self, store: SQLiteWritingDataStore, project_id: str, revision_id: str
    ) -> list[str]:
        jobs = [
            job for job in store.list_outbox_jobs(project_id) if job.aggregate_id == revision_id
        ]
        return sorted(job.job_type for job in jobs)

    def test_manual_edit_schedules_full_revision_pipeline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, scene_id = self._seed_accepted_scene(temp_dir)
            updated = store.update_manuscript_scene(
                project_id,
                scene_id,
                ManuscriptSceneUpdate(
                    expected_scene_version=1,
                    title="Opening Draft Revised",
                    content="# Opening Draft Revised\n\nMira tests the sealed doors again.",
                ),
            )
            latest = next(
                revision
                for revision in store.list_manuscript_revisions(project_id)
                if revision.version == 2
            )
            job_types = self._job_types_for_revision(store, project_id, latest.id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.version, 2)
        self.assertEqual(
            latest.content, "# Opening Draft Revised\n\nMira tests the sealed doors again."
        )
        self.assertEqual(job_types, REVISION_JOB_TYPES)

    def test_restore_schedules_full_revision_pipeline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, scene_id = self._seed_accepted_scene(temp_dir)
            store.update_manuscript_scene(
                project_id,
                scene_id,
                ManuscriptSceneUpdate(
                    expected_scene_version=1,
                    title="Opening Draft Revised",
                    content="# Opening Draft Revised\n\nRewritten prose.",
                ),
            )
            first_revision = next(
                revision
                for revision in store.list_manuscript_revisions(project_id)
                if revision.version == 1
            )
            restored = store.restore_manuscript_revision(project_id, first_revision.id)
            latest = next(
                revision
                for revision in store.list_manuscript_revisions(project_id)
                if revision.version == 3
            )
            job_types = self._job_types_for_revision(store, project_id, latest.id)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.version, 3)
        self.assertEqual(latest.content, first_revision.content)
        self.assertEqual(job_types, REVISION_JOB_TYPES)

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
                    expected_scene_version=1,
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
                    expected_scene_version=1,
                    title="No Scene",
                    content="This should not be saved.",
                ),
            )

        self.assertIsNone(updated)


if __name__ == "__main__":
    unittest.main()
