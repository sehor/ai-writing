from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from app.data import SQLiteWritingDataStore
from app.cognition.interfaces import CommittedContentEvent
from app.cognition.registry import CognitionRegistry
from app.cognition.snapshots import build_project_snapshot
from app.models import (
    CanonEntityCreate,
    ManuscriptProposalCreate,
    MemoryRecordCreate,
    ProjectCreate,
    SceneContractCreate,
    SnowflakeArtifact,
)
from app.exports.wiki import build_wiki_export


class WikiExportTests(unittest.TestCase):
    def test_export_builds_interlinked_markdown_wiki_package(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Wiki Smoke",
                    premise="A cartographer maps a city that edits memory.",
                )
            )
            store.save_snowflake_artifact(
                SnowflakeArtifact(
                    project_id=project.id,
                    step_number=8,
                    artifact="scene_contracts",
                    content="Scene list for the city archive.",
                )
            )
            canon = store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Mira",
                    summary="Disgraced cartographer.",
                    current_state="Searching the archive.",
                    constraints="Must not know who altered the city map.",
                    last_seen="scene_001",
                    timeline_notes="Entered the archive at dusk.",
                ),
            )
            memory = store.create_memory_record(
                project.id,
                MemoryRecordCreate(
                    record_type="voice_sample",
                    title="Mira clipped voice",
                    scope="Mira",
                    content="Short sentences under pressure.",
                    tags="Mira, tension",
                    source_ref="step 8",
                ),
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=1,
                    title="Archive Door",
                    pov="Mira",
                    goal="Open the archive door.",
                    conflict="The lock rejects her map.",
                    turning_point="The map redraws itself.",
                    required_canon="Mira must not know who altered the city map.",
                    forbidden_facts="The patron's identity.",
                    open_threads="Who changed the map?",
                    source_artifact_step=8,
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="1. Archive Door",
                    content="Mira pressed the map to the lock.",
                    context="Compiled context.",
                    checklist=["Canon reviewed"],
                ),
            )
            store.accept_manuscript_proposal(project.id, proposal.id)
            store.list_manuscript_revisions(project.id)

            export = build_wiki_export(
                project,
                store.list_snowflake_artifacts(project.id),
                store.list_canon_entities(project.id),
                store.list_scene_contracts(project.id),
                store.list_memory_records(project.id),
                store.list_manuscript_scenes(project.id),
            )

        files = {file.path: file.content for file in export.files}
        self.assertIn("SCHEMA.md", files)
        self.assertIn("index.md", files)
        self.assertIn("log.md", files)
        self.assertIn("project.md", files)
        self.assertIn("graph.md", files)
        self.assertIn("raw/project-state.json", files)
        entity_path = f"entities/character-mira-{canon.id}.md"
        memory_path = f"memory/voice_sample-mira-clipped-voice-{memory.id}.md"
        scene_path = f"scenes/001-archive-door-{scene.id}.md"
        self.assertIn(entity_path, files)
        self.assertIn(memory_path, files)
        self.assertIn(scene_path, files)

        index = files["index.md"]
        self.assertIn(f"[[{entity_path.removesuffix('.md')}|Mira]]", index)
        self.assertIn(f"[[{scene_path.removesuffix('.md')}|1. Archive Door]]", index)

        scene_page = files[scene_path]
        self.assertIn(f"[[{entity_path.removesuffix('.md')}|Mira]]", scene_page)
        self.assertIn("[[artifacts/step-8-scene-contracts|Step 8: scene_contracts]]", scene_page)

        entity_page = files[entity_path]
        self.assertIn(
            f"[[{scene_path.removesuffix('.md')}|1. Archive Door]]",
            entity_page,
        )

        snapshot = json.loads(files["raw/project-state.json"])
        self.assertEqual(snapshot["project"]["id"], project.id)
        self.assertEqual(snapshot["canon_entities"][0]["id"], canon.id)
        self.assertEqual(snapshot["memory_records"][0]["id"], memory.id)
        self.assertEqual(export.file_count, len(export.files))

    def test_cognition_registry_does_not_manage_llm_wiki_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = SQLiteWritingDataStore(root / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Module Smoke",
                    premise="A city remembers only approved drafts.",
                )
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=1,
                    title="Memory Gate",
                    pov="Mira",
                    goal="Cross the gate.",
                    conflict="The gate asks for a true memory.",
                    turning_point="Mira gives it a false one.",
                    required_canon="Mira is the POV.",
                    forbidden_facts="",
                    open_threads="What did the gate keep?",
                    source_artifact_step=8,
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="1. Memory Gate",
                    content="POV: Mira\n\nMira crossed the gate.",
                    context="Compiled context.",
                    checklist=["Canon reviewed"],
                ),
            )
            store.accept_manuscript_proposal(project.id, proposal.id)
            revision = store.list_manuscript_revisions(project.id)[0]
            registry = CognitionRegistry(root / "projects")

            reports = registry.ingest_committed_content(
                build_project_snapshot(project.id, store),
                CommittedContentEvent(
                    source="manuscript_revision",
                    source_ref=f"manuscript_revision:{revision.id}",
                    title=revision.title,
                    content=revision.content,
                    revision=revision,
                ),
            )

            memplace_path = root / "projects" / project.id / "modules" / "memplace"
            llm_wiki_path = root / "projects" / project.id / "modules" / "llm_wiki"
            self.assertFalse(llm_wiki_path.exists())
            self.assertTrue((memplace_path / "prose_samples").is_dir())
            proposals = [proposal for report in reports for proposal in report.writeback_proposals]
            self.assertEqual({proposal.target for proposal in proposals}, {"memory_record"})


if __name__ == "__main__":
    unittest.main()
