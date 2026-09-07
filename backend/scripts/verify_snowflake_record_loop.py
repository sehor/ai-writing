"""Executable business smoke-check for the Step 6-9 record authority loop."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.writing_workflow import (
    LocalDraftWritingWorkflow,
    ProjectContextLoader,
    WritingWorkflowState,
)
from app.data import SQLiteWritingDataStore
from app.data.flows import SnowflakeRevisionValidationError
from app.llm_wiki.local_backend import LocalFileLlmWiki
from app.models import (
    CanonEntityCreate,
    ProjectCreate,
    SnowflakeArtifactRevisionCreate,
    SnowflakeGenerationCreate,
    SnowflakeGenerationRequest,
    SnowflakeRecordDecisionRequest,
    SnowflakeRecordRevisionCreate,
)
from app.services.snowflake_compile_service import SnowflakeCompileService
from app.services.snowflake_service import (
    SNOWFLAKE_STEPS,
    SnowflakeRecordValidationError,
    SnowflakeService,
)


def main() -> None:
    with TemporaryDirectory(prefix="snowflake-record-loop-") as temp_dir:
        root = Path(temp_dir)
        store = SQLiteWritingDataStore(root / "app.db")
        store.init()
        project = store.create_project(
            ProjectCreate(title="Record Authority Smoke", premise="Mira maps a living city.")
        )
        wiki = LocalFileLlmWiki(root / "wiki")
        service = SnowflakeService(store, wiki)
        compiler = SnowflakeCompileService(store)

        character_payload = {
            "record_type": "character",
            "name": "Mira",
            "role": "protagonist",
            "one_sentence_summary": "A cartographer in exile.",
            "motivation": "Restore her place in the city.",
            "goal": "Reach the archive.",
            "conflict": "The streets rewrite themselves.",
            "epiphany": "A changing map can still be home.",
            "viewpoint_summary": "Mira distrusts every route after exile.",
            "confirmed_facts": ["Mira is a cartographer in exile."],
        }
        character = service.create_record_revision(
            project.id,
            SnowflakeRecordRevisionCreate(
                step_number=7,
                record_id="character-mira",
                payload=character_payload,
            ),
        )
        accepted_character = service.decide_record_revision(
            project.id,
            character.id,
            SnowflakeRecordDecisionRequest(decision="accepted", expected_revision_id=""),
        ).revision
        poisoned_payload = dict(character_payload)
        poisoned_payload["confirmed_facts"] = ["UNACCEPTED POISON FACT"]
        service.create_record_revision(
            project.id,
            SnowflakeRecordRevisionCreate(
                step_number=7,
                record_id="character-mira",
                payload=poisoned_payload,
                base_revision_id=accepted_character.id,
                source="ai",
            ),
        )
        canon_report = compiler.extract_canon_proposals(project.id)
        canon_output = json.dumps(
            [proposal.model_dump() for proposal in canon_report.proposals],
            ensure_ascii=False,
        )
        assert "Mira is a cartographer in exile" in canon_output
        assert "UNACCEPTED POISON FACT" not in canon_output

        scene_payload = {
            "title": "Opening",
            "pov": "Mira",
            "goal": "Reach the archive before dusk.",
            "conflict": "The gate is sealed.",
            "turning_point": "Mira burns her only map.",
            "outcome": "The gate opens, but she cannot return.",
            "required_canon_ids": [],
            "forbidden_facts": [],
            "information_delta": "The archive demands a sacrifice.",
            "character_state_delta": "Mira loses trust in fixed routes.",
            "story_thread_actions": [],
        }
        scene = service.create_record_revision(
            project.id,
            SnowflakeRecordRevisionCreate(
                step_number=8,
                record_id="scene-opening",
                position=1,
                payload=scene_payload,
            ),
        )
        service.decide_record_revision(
            project.id,
            scene.id,
            SnowflakeRecordDecisionRequest(decision="accepted", expected_revision_id=""),
        )
        scene_report = compiler.parse_scene_proposals(project.id)
        assert scene_report.proposals[0].information_delta == scene_payload["information_delta"]
        assert (
            scene_report.proposals[0].character_state_delta
            == scene_payload["character_state_delta"]
        )

        invalid_payload = dict(scene_payload)
        invalid_payload["required_canon_ids"] = ["missing-canon-id"]
        invalid = service.create_record_revision(
            project.id,
            SnowflakeRecordRevisionCreate(
                step_number=8,
                record_id="scene-invalid-reference",
                position=2,
                payload=invalid_payload,
            ),
        )
        try:
            service.decide_record_revision(
                project.id,
                invalid.id,
                SnowflakeRecordDecisionRequest(decision="accepted", expected_revision_id=""),
            )
        except SnowflakeRecordValidationError as exc:
            assert exc.report.findings[0].code == "unknown_required_canon"
        else:
            raise AssertionError("Unknown Canon reference reached an accepted record head.")

        blob = service.create_revision(
            project.id,
            SnowflakeArtifactRevisionCreate(
                step_number=8,
                content=json.dumps({"records": []}),
            ),
        )
        accepted_step8_head = next(
            head for head in store.list_snowflake_heads(project.id) if head.step_number == 8
        )
        try:
            store.decide_snowflake_revision(
                project_id=project.id,
                revision_id=blob.id,
                decision="accepted",
                expected_head_revision_id=accepted_step8_head.accepted_revision_id,
            )
        except SnowflakeRevisionValidationError as exc:
            assert exc.report.findings[0].code == "record_authority_required"
        else:
            raise AssertionError("Step 8 blob Artifact became an accepted head.")

        store.create_canon_entity(
            project.id,
            CanonEntityCreate(
                entity_type="character",
                name="Mira",
                constraints="Mira cannot fly.",
            ),
        )
        workflow = LocalDraftWritingWorkflow(store, SNOWFLAKE_STEPS, wiki)
        artifact_revision_count_before = len(store.list_snowflake_revisions(project.id, 9)[0])
        generated = service.generate_revision(
            project.id,
            SnowflakeGenerationCreate(
                step_number=9,
                instruction="Mira will fly across the wall.",
                generation_mode="record_set",
            ),
            workflow,
        )
        artifact_revision_count_after = len(store.list_snowflake_revisions(project.id, 9)[0])
        assert generated.revision is None and generated.record_revisions
        assert artifact_revision_count_after == artifact_revision_count_before
        assert any(
            finding.code == "canon_constraint_conflict"
            for finding in generated.validation_report.findings
        )

        context = ProjectContextLoader(store, SNOWFLAKE_STEPS).run(
            WritingWorkflowState(
                request=SnowflakeGenerationRequest(
                    project_id=project.id,
                    step_number=8,
                    user_input="Develop Mira's accepted profile.",
                    generation_mode="record_set",
                )
            )
        )
        assert context.previous_records[7][0].id == accepted_character.id
        assert "UNACCEPTED" not in json.dumps(
            context.previous_records[7][0].payload, ensure_ascii=False
        )

        with store.connect() as connection:
            derived_rows = connection.execute(
                """
                SELECT step_number, id, structured_payload
                FROM snowflake_artifact_revisions
                WHERE project_id = ? AND step_number IN (7, 8)
                  AND status = 'accepted' AND source = 'derived'
                ORDER BY step_number, revision_no DESC
                """,
                (project.id,),
            ).fetchall()
            accepted_record_ids = {
                row["accepted_revision_id"]
                for row in connection.execute(
                    """
                    SELECT accepted_revision_id FROM snowflake_record_heads
                    WHERE project_id = ? AND accepted_revision_id <> ''
                    """,
                    (project.id,),
                ).fetchall()
            }
        assert {7, 8}.issubset({row["step_number"] for row in derived_rows})
        projected_record_ids = {
            record["revision_id"]
            for row in derived_rows
            for record in json.loads(row["structured_payload"])["records"]
        }
        assert accepted_record_ids.issubset(projected_record_ids)

        print(
            json.dumps(
                {
                    "record_authority": "passed",
                    "canon_compiler_source": "accepted Step 7 record heads",
                    "scene_compiler_source": "accepted Step 8 record heads",
                    "unaccepted_poison_excluded": True,
                    "invalid_reference_blocked_before_accept": True,
                    "blob_acceptance_blocked": True,
                    "generation_created_blob_revision": False,
                    "canon_consistency_finding": True,
                    "derived_projection_steps": sorted(
                        {row["step_number"] for row in derived_rows}
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
