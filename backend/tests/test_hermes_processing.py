from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.models import (
    ManuscriptProposalCreate,
    ProjectCreate,
    SceneContractCreate,
)
from app.agents.hermes_client import HermesAgentClient
from app.agents.writeback_workflow import validate_writeback_payload


class RecordingHermesTransport:
    def __init__(self) -> None:
        self.path = ""
        self.payload = {}

    def post_json(self, path, payload):
        self.path = path
        self.payload = payload
        return {
            "status": "completed",
            "summary": "recorded",
            "wiki_changes": [],
            "issues": [],
            "writeback_proposals": [],
            "processed_source_ref": payload["source_ref"],
        }


class HermesProcessingTests(unittest.TestCase):
    def test_process_revision_sends_delta_to_virtual_hermes_and_stores_proposals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(
                    title="Hermes Smoke",
                    premise="A cartographer tests an external wiki worker.",
                )
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=1,
                    title="Compass Door",
                    pov="Mira",
                    goal="Open the compass door.",
                    conflict="The lock rejects her map.",
                    turning_point="Mira hears the compass answer.",
                    required_canon="Mira is the POV.",
                    forbidden_facts="the patron identity",
                    open_threads="Who made the compass?",
                    source_artifact_step=8,
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="1. Compass Door",
                    content="Mira listens to the compass and keeps the patron identity hidden.",
                    context="Compiled context.",
                    checklist=["Canon reviewed"],
                ),
            )
            store.accept_manuscript_proposal(project.id, proposal.id)
            revision = store.list_manuscript_revisions(project.id)[0]

            result = HermesAgentClient().process_manuscript_revision(
                project_id=project.id,
                project_title=project.title,
                revision=revision,
                scene_contract=scene,
            )
            for writeback in result.writeback_proposals:
                validate_writeback_payload(writeback)
                store.create_writeback_proposal(project.id, writeback)
            stored = store.list_writeback_proposals(project.id)

        self.assertEqual(result.processed_source_ref, f"manuscript_revision:{revision.id}")
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.wiki_changes), 3)
        self.assertEqual(len(result.writeback_proposals), 1)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].target, "memory_record")
        self.assertEqual(result.issues[0].code, "scene_contract_forbidden_fact")

    def test_client_posts_only_revision_delta_and_scene_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(title="Delta Smoke", premise="Test delta payload.")
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=2,
                    title="Narrow Payload",
                    pov="Mira",
                    goal="Send only the new chapter.",
                    conflict="Avoid global context upload.",
                    turning_point="Hermes accepts the event.",
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title="2. Narrow Payload",
                    content="Mira sends only this scene.",
                    context="Compiled context.",
                    checklist=["reviewed"],
                ),
            )
            store.accept_manuscript_proposal(project.id, proposal.id)
            revision = store.list_manuscript_revisions(project.id)[0]
            transport = RecordingHermesTransport()

            HermesAgentClient(transport).process_manuscript_revision(
                project.id,
                project.title,
                revision,
                scene,
            )

        self.assertEqual(transport.path, "/agent/tasks/process-manuscript-revision")
        self.assertEqual(
            set(transport.payload),
            {"task", "project", "revision", "scene_contract", "source_ref", "idempotency_key"},
        )
        self.assertNotIn("snapshot", transport.payload)
        self.assertNotIn("wiki", transport.payload)


if __name__ == "__main__":
    unittest.main()
