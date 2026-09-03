from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.data.flows import SnowflakeHeadConflictError
from app.llm_wiki.stage_protocol import get_stage_policy
from app.models import (
    ProjectCreate,
    SnowflakeArtifact,
    SnowflakeArtifactRevisionCreate,
    SnowflakeRecordRevisionCreate,
)
from app.snowflake.dependencies import downstream_steps
from app.snowflake.step_spec import SNOWFLAKE_STEP_SPECS, validate_step_graph


class SnowflakeStepSpecTests(unittest.TestCase):
    def test_specs_are_complete_acyclic_and_drive_wiki_policy(self) -> None:
        validate_step_graph()
        self.assertEqual([spec.number for spec in SNOWFLAKE_STEP_SPECS], list(range(1, 11)))
        for spec in SNOWFLAKE_STEP_SPECS:
            policy = get_stage_policy(spec.number)
            self.assertEqual(policy.artifact_type, spec.artifact_type)
            self.assertEqual(policy.planned_source_steps, spec.dependencies)

    def test_dependency_closure_reaches_manuscript_readiness(self) -> None:
        affected = downstream_steps(2)
        for step in (3, 4, 5, 6, 7, 8, 9, 10):
            self.assertIn(step, affected)
        self.assertNotIn(1, affected)


class SnowflakeRevisionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.store = SQLiteWritingDataStore(Path(self.temp.name) / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Revision Novel", premise="A revision-safe story.")
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create(self, step: int, content: str):
        payload = {}
        if step == 2:
            payload = {
                name: {
                    "beat_id": name,
                    "event": f"{name} event",
                    "cause": f"{name} cause",
                    "protagonist_action": f"{name} action",
                    "escalation": "Escalates the prior disaster" if name in {"disaster_2", "disaster_3"} else "",
                }
                for name in ("setup", "disaster_1", "disaster_2", "disaster_3", "ending")
            }
        elif step == 4:
            payload = {
                "paragraphs": [
                    {"beat_id": beat, "text": f"Expanded {beat}."}
                    for beat in ("setup", "disaster_1", "disaster_2", "disaster_3", "ending")
                ]
            }
        return self.store.create_snowflake_revision(
            self.project.id,
            SnowflakeArtifactRevisionCreate(
                step_number=step, content=content, structured_payload=payload
            ),
        )

    def accept(self, revision, expected: str = ""):
        return self.store.decide_snowflake_revision(
            project_id=self.project.id,
            revision_id=revision.id,
            decision="accepted",
            expected_head_revision_id=expected,
        )

    def test_draft_does_not_commit_until_acceptance(self) -> None:
        revision = self.create(1, "A mapmaker must stop a city from erasing its people.")
        self.assertEqual(revision.status, "draft")
        self.assertIsNone(self.store.get_snowflake_artifact(self.project.id, 1))
        self.assertEqual(self.store.get_project(self.project.id).current_step, 1)

        accepted, head, affected, job_id = self.accept(revision)
        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(head.accepted_revision_id, revision.id)
        self.assertTrue(job_id)
        self.assertIn(10, affected)
        self.assertEqual(self.store.get_snowflake_artifact(self.project.id, 1).content, revision.content)
        self.assertEqual(self.store.get_project(self.project.id).current_step, 2)

    def test_reject_preserves_accepted_head(self) -> None:
        first = self.create(1, "First accepted promise.")
        self.accept(first)
        proposal = self.create(1, "Rejected replacement.")
        rejected, head, affected, job_id = self.store.decide_snowflake_revision(
            project_id=self.project.id,
            revision_id=proposal.id,
            decision="rejected",
            expected_head_revision_id=first.id,
        )
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(head.accepted_revision_id, first.id)
        self.assertEqual(affected, [])
        self.assertEqual(job_id, "")
        self.assertEqual(self.store.get_snowflake_artifact(self.project.id, 1).content, first.content)

    def test_acceptance_uses_optimistic_concurrency_and_marks_downstream_stale(self) -> None:
        step_two = self.create(2, "Initial paragraph.")
        self.accept(step_two)
        step_four = self.create(4, "Initial synopsis.")
        self.accept(step_four)
        replacement = self.create(2, "Revised paragraph.")

        with self.assertRaises(SnowflakeHeadConflictError):
            self.accept(replacement, expected="")

        accepted, _head, affected, _job_id = self.accept(replacement, expected=step_two.id)
        self.assertEqual(accepted.status, "accepted")
        self.assertIn(4, affected)
        states = {head.step_number: head for head in self.store.list_snowflake_heads(self.project.id)}
        self.assertEqual(states[4].state, "stale")
        self.assertEqual(states[4].accepted_revision_id, step_four.id)
        self.assertEqual(states[10].state, "stale")

    def test_revision_history_is_append_only_and_paginated(self) -> None:
        first = self.create(3, "Character version one.")
        second = self.create(3, "Character version two.")
        revisions, total = self.store.list_snowflake_revisions(
            self.project.id, 3, limit=1, offset=0
        )
        self.assertEqual(total, 2)
        self.assertEqual(revisions[0].id, second.id)
        self.assertEqual((first.revision_no, second.revision_no), (1, 2))

    def test_only_optional_step_can_be_skipped(self) -> None:
        head = self.store.skip_snowflake_step(self.project.id, 9)
        self.assertEqual(head.state, "skipped")
        with self.assertRaises(ValueError):
            self.store.skip_snowflake_step(self.project.id, 8)

    def test_step_six_records_are_paginated_and_independently_revised(self) -> None:
        first = self.store.create_snowflake_record_revision(
            self.project.id,
            SnowflakeRecordRevisionCreate(
                step_number=6,
                record_id="act-1-sequence-1",
                position=1,
                payload={
                    "record_id": "act-1-sequence-1",
                    "act": "Act I",
                    "section": "Opening",
                    "sequence": 1,
                    "synopsis": "Opening sequence",
                    "step4_paragraph_refs": ["setup"],
                    "character_refs": ["protagonist"],
                },
            ),
        )
        accepted = self.store.decide_snowflake_record_revision(
            self.project.id,
            first.id,
            decision="accepted",
            expected_revision_id="",
        )
        second = self.store.create_snowflake_record_revision(
            self.project.id,
            SnowflakeRecordRevisionCreate(
                step_number=6,
                record_id="act-1-sequence-1",
                position=1,
                payload={
                    "record_id": "act-1-sequence-1",
                    "act": "Act I",
                    "section": "Opening",
                    "sequence": 1,
                    "synopsis": "Revised opening sequence",
                    "step4_paragraph_refs": ["setup"],
                    "character_refs": ["protagonist"],
                },
                base_revision_id=accepted.revision.id,
            ),
        )
        self.store.create_snowflake_record_revision(
            self.project.id,
            SnowflakeRecordRevisionCreate(
                step_number=6,
                record_id="act-1-sequence-2",
                position=2,
                payload={
                    "record_id": "act-1-sequence-2",
                    "act": "Act I",
                    "section": "Opening",
                    "sequence": 2,
                    "synopsis": "Second sequence",
                    "step4_paragraph_refs": ["disaster_1"],
                    "character_refs": ["protagonist"],
                },
            ),
        )

        page, total = self.store.list_snowflake_records(
            self.project.id, 6, limit=1, offset=0
        )
        self.assertEqual(total, 2)
        self.assertEqual(page[0].record_id, "act-1-sequence-1")
        self.assertEqual(page[0].id, second.id)
        self.assertEqual(second.revision_no, 2)
        history, history_total = self.store.list_snowflake_record_revisions(
            self.project.id, 6, "act-1-sequence-1", limit=10, offset=0
        )
        self.assertEqual(history_total, 2)
        self.assertEqual([item.revision_no for item in history], [2, 1])

    def test_record_decision_detects_changed_head(self) -> None:
        revision = self.store.create_snowflake_record_revision(
            self.project.id,
            SnowflakeRecordRevisionCreate(
                step_number=8,
                record_id="scene-1",
                payload={"title": "Opening"},
            ),
        )
        with self.assertRaises(ValueError):
            self.store.decide_snowflake_record_revision(
                self.project.id,
                revision.id,
                decision="accepted",
                expected_revision_id="unexpected",
            )


class SnowflakeLegacyMigrationTests(unittest.TestCase):
    def test_legacy_step_ten_is_preserved_without_becoming_an_accepted_head(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.db"
            store = SQLiteWritingDataStore(path)
            store.init()
            store.save_snowflake_artifact(
                SnowflakeArtifact(
                    project_id="demo-novel",
                    step_number=10,
                    artifact="manuscript",
                    content="Legacy full manuscript.",
                )
            )
            with store.connect() as connection:
                connection.execute("DELETE FROM schema_migrations WHERE version = 9")
                connection.execute("DROP TABLE snowflake_artifact_heads")
                connection.execute("DROP TABLE snowflake_artifact_revisions")
            store.init()
            revisions, total = store.list_snowflake_revisions(
                "demo-novel", 10, limit=20, offset=0
            )
            self.assertEqual(total, 1)
            self.assertEqual(revisions[0].status, "legacy_draft")
            step_ten = store.list_snowflake_heads("demo-novel")[9]
            self.assertEqual(step_ten.state, "missing")
            self.assertEqual(step_ten.accepted_revision_id, "")


if __name__ == "__main__":
    unittest.main()
