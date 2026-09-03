import json
import unittest

from pydantic import ValidationError

from app.agents.deepseek_workflow import format_previous_artifacts
from app.agents.writing_workflow import LocalConsistencyReviewer, WritingWorkflowState
from app.models import (
    CanonEntity,
    SnowflakeArtifact,
    SnowflakeGenerationCreate,
    SnowflakeGenerationRequest,
)


def artifact(step_number: int, content: str) -> SnowflakeArtifact:
    return SnowflakeArtifact(
        project_id="context-budget-project",
        step_number=step_number,
        artifact=f"artifact-{step_number}",
        content=content,
    )


class DeepSeekContextBudgetTests(unittest.TestCase):
    def test_previous_artifacts_are_not_truncated_individually(self) -> None:
        context = format_previous_artifacts(
            [
                artifact(1, f"{'A' * 5000}END_ONE"),
                artifact(2, f"{'B' * 5000}END_TWO"),
            ],
            max_chars=12000,
        )

        self.assertIn("END_ONE", context)
        self.assertIn("END_TWO", context)
        self.assertFalse(context.endswith("..."))

    def test_custom_budget_caps_the_combined_context_and_keeps_recent_steps_first(self) -> None:
        context = format_previous_artifacts(
            [
                artifact(1, "older" * 2000),
                artifact(2, "recent" * 2000),
            ],
            max_chars=6000,
        )

        self.assertEqual(len(context), 6000)
        self.assertTrue(context.startswith("### Step 2: artifact-2"))
        self.assertNotIn("### Step 1: artifact-1", context)
        self.assertTrue(context.endswith("..."))

    def test_generation_contract_has_a_bounded_user_configurable_budget(self) -> None:
        create = SnowflakeGenerationCreate(step_number=2, instruction="Expand the premise.")
        request = SnowflakeGenerationRequest(
            project_id="context-budget-project",
            step_number=2,
            user_input="Expand the premise.",
            previous_artifacts_context_chars=125000,
        )

        self.assertEqual(create.previous_artifacts_context_chars, 64000)
        self.assertEqual(request.previous_artifacts_context_chars, 125000)
        with self.assertRaises(ValidationError):
            SnowflakeGenerationCreate(
                step_number=2,
                instruction="Too small.",
                previous_artifacts_context_chars=999,
            )
        with self.assertRaises(ValidationError):
            SnowflakeGenerationCreate(
                step_number=2,
                instruction="Too large.",
                previous_artifacts_context_chars=400001,
            )

    def test_consistency_reviewer_reports_canon_capability_conflict_with_evidence(self) -> None:
        payload = {
            "title": "Impossible Escape",
            "pov": "Mira",
            "goal": "Mira will fly over the wall.",
            "conflict": "The gate is sealed.",
            "turning_point": "Mira begins to fly.",
            "outcome": "Mira crosses the wall.",
            "required_canon_ids": [],
            "forbidden_facts": [],
            "information_delta": "Mira sees the outer district.",
            "character_state_delta": "Mira becomes confident.",
            "story_thread_actions": [],
        }
        state = WritingWorkflowState(
            request=SnowflakeGenerationRequest(
                project_id="context-budget-project",
                step_number=8,
                user_input="Draft the escape.",
                generation_mode="record_set",
            ),
            content=json.dumps(
                {"records": [{"record_id": "scene-impossible", "payload": payload}]}
            ),
            canon_entities=[
                CanonEntity(
                    id="canon-mira",
                    project_id="context-budget-project",
                    entity_type="character",
                    name="Mira",
                    constraints="Mira cannot fly.",
                )
            ],
        )

        reviewed = LocalConsistencyReviewer().run(state)

        self.assertEqual(reviewed.validation_report.status, "warnings")
        finding = next(
            item
            for item in reviewed.validation_report.findings
            if item.code == "canon_constraint_conflict"
        )
        self.assertIn("fly", finding.evidence)
        self.assertEqual(reviewed.trace[-1].agent_name, "consistency_reviewer")
        self.assertEqual(reviewed.trace[-1].status, "warnings")


if __name__ == "__main__":
    unittest.main()
