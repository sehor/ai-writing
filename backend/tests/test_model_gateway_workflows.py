from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from app.agents.reference_workflow import generate_gateway_reference_suggestion
from app.agents.manuscript_workflow import generate_manuscript_scene
from app.agents.snowflake_workflow import SnowflakeWorkflow
from app.agents.writeback_workflow import generate_gateway_writeback_proposals
from app.cognition.snapshots import build_project_snapshot
from app.data import SQLiteWritingDataStore
from app.llm import FakeModelGateway, ModelGatewayError
from app.llm_wiki.local_backend import LocalFileLlmWiki
from app.models import (
    ManuscriptRevision,
    ProjectCreate,
    ReferenceGenerationRequest,
    SnowflakeGenerationRequest,
)
from app.services.snowflake_service import SNOWFLAKE_STEPS


class ModelGatewayWorkflowTests(unittest.TestCase):
    def test_manuscript_workflow_preserves_structured_step_ten_proposals(self) -> None:
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "scene_id": "scene-1",
                        "manuscript_prose": "Mira opens the sealed archive.",
                        "entry_state_observed": ["The archive is sealed."],
                        "exit_state_produced": ["The archive is open."],
                        "scene_contract_coverage": {
                            "goal": "Open the archive.",
                            "conflict": "The lock resists her key.",
                            "turning_point": "The key breaks the ward.",
                            "outcome": "The archive opens.",
                            "missing_elements": [],
                        },
                        "new_fact_candidates": [
                            {
                                "claim": "The key can break archive wards.",
                                "entity_refs": ["key", "archive"],
                                "reason_introduced": "Required by the scene turning point.",
                                "status": "proposal",
                            }
                        ],
                        "design_deviation_proposals": [],
                        "continuity_questions": [],
                        "source_refs": ["scene_contract:scene-1"],
                    }
                )
            ]
        )

        result = generate_manuscript_scene(gateway, "Approved scene context.")

        self.assertEqual(result.validated_value.scene_id, "scene-1")
        self.assertEqual(len(result.validated_value.new_fact_candidates), 1)
        self.assertEqual(result.completion.request.prompt.prompt_version, "2.0.0")

    def test_snowflake_workflow_compiles_calls_validates_and_traces(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Gateway", premise="A guarded city."))
            gateway = FakeModelGateway(
                [
                    json.dumps(
                        {
                            "protagonist": "Mira",
                            "story_goal_or_problem": "Open the archive",
                            "opposition_or_stakes": "The city will erase her name",
                            "promise": "Mira must open the archive before the city erases her name.",
                        }
                    )
                ]
            )
            workflow = SnowflakeWorkflow(
                store,
                SNOWFLAKE_STEPS,
                gateway,
                LocalFileLlmWiki(Path(temp_dir) / "wiki"),
            )

            result = workflow.run_snowflake_generation(
                SnowflakeGenerationRequest(
                    project_id=project.id,
                    step_number=1,
                    user_input="Create the promise.",
                )
            )

        self.assertEqual(gateway.requests[0].prompt.prompt_id, "snowflake.step01")
        self.assertEqual(result.validation_report.status, "passed")
        model_trace = next(item for item in result.workflow_trace if item.agent_name == "model_gateway")
        self.assertEqual(model_trace.provider_id, "fake")
        self.assertEqual(model_trace.prompt_version, "2.0.0")

    def test_reference_gateway_result_remains_a_pending_advisory_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Reference", premise="A lost map."))
            snapshot = build_project_snapshot(project.id, store)
            request = ReferenceGenerationRequest(author_problem="How can the map mislead the hero?")
            gateway = FakeModelGateway(["Three reviewable possibilities."])

            generated = generate_gateway_reference_suggestion(
                gateway,
                request,
                "assembled context",
                snapshot,
                [],
            )

        self.assertEqual(generated.suggestion.content, "Three reviewable possibilities.")
        self.assertEqual(generated.completion.request.prompt.prompt_id, "reference.suggestion")
        trace = generated.suggestion.workflow_trace[1]
        self.assertEqual(trace.provider_id, "fake")
        self.assertEqual(generated.suggestion.proposed_writebacks, [])

    def test_writeback_gateway_parses_and_validates_before_returning_proposals(self) -> None:
        revision = ManuscriptRevision(
            id="revision-1",
            project_id="project-1",
            scene_id="scene-1",
            proposal_id="proposal-1",
            title="Arrival",
            content="Mira pockets the brass key.",
            version=1,
            created_at="2026-09-04T00:00:00Z",
        )
        source_ref = "manuscript_revision:revision-1"
        gateway = FakeModelGateway(
            [
                json.dumps(
                    [
                        {
                            "target": "memory_record",
                            "action": "create",
                            "title": "Arrival summary",
                            "rationale": "The accepted revision establishes the key.",
                            "source_ref": source_ref,
                            "payload": {
                                "record_type": "chapter_summary",
                                "title": "Arrival summary",
                                "content": "Mira pockets the brass key.",
                                "source_ref": source_ref,
                            },
                        }
                    ]
                )
            ]
        )

        generated = generate_gateway_writeback_proposals(gateway, revision, [], [])

        self.assertEqual(len(generated.proposals), 1)
        self.assertEqual(generated.proposals[0].target, "memory_record")
        self.assertEqual(generated.completion.request.prompt.prompt_id, "writeback.propose")

    def test_invalid_writeback_output_fails_before_a_proposal_is_returned(self) -> None:
        revision = ManuscriptRevision(
            id="revision-1",
            project_id="project-1",
            scene_id="scene-1",
            proposal_id="proposal-1",
            title="Arrival",
            content="Draft",
            version=1,
            created_at="2026-09-04T00:00:00Z",
        )
        gateway = FakeModelGateway(["not-json"])
        with self.assertRaises(ModelGatewayError):
            generate_gateway_writeback_proposals(gateway, revision, [], [])


if __name__ == "__main__":
    unittest.main()
