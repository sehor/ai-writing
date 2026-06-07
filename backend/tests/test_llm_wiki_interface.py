from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.llm_wiki.interfaces import (
    LlmWiki,
    WikiContextQuery,
    WikiInsightQuery,
    WikiSourceDocument,
)
from app.llm_wiki.local_backend import LocalFileLlmWiki
from app.llm_wiki.stage_protocol import get_stage_policy


class LlmWikiInterfaceTests(unittest.TestCase):
    def test_stage_policy_limits_planned_sources_and_observed_visibility(self) -> None:
        step_two = get_stage_policy(2)
        step_nine = get_stage_policy(9)
        step_ten = get_stage_policy(10)

        self.assertEqual(step_two.planned_source_steps, (1,))
        self.assertEqual(step_nine.planned_source_steps, (6, 7, 8))
        self.assertFalse(step_nine.include_observed)
        self.assertEqual(step_ten.planned_source_steps, (8, 9))
        self.assertTrue(step_ten.include_observed)

    def test_interface_dtos_do_not_expose_application_owned_state(self) -> None:
        dto_types = [
            WikiSourceDocument,
            WikiContextQuery,
            WikiInsightQuery,
        ]
        forbidden_fragments = {
            "snapshot",
            "canon",
            "memory",
            "cognition",
            "deepseek",
            "provider",
            "data_store",
        }

        for dto_type in dto_types:
            field_names = set(dto_type.model_fields)
            self.assertFalse(
                any(
                    fragment in field_name
                    for field_name in field_names
                    for fragment in forbidden_fragments
                ),
                f"{dto_type.__name__} leaks app-owned state: {field_names}",
            )

        self.assertTrue(hasattr(LlmWiki, "ingest"))
        self.assertTrue(hasattr(LlmWiki, "retrieve_context"))
        self.assertTrue(hasattr(LlmWiki, "analyze"))

    def test_local_backend_separates_planned_and_observed_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:8",
                    title="Scene list",
                    content="Mira plans to enter the archive.",
                    snowflake_step=8,
                    artifact_type="scene_contracts",
                    knowledge_class="planned",
                    scope="scene-1",
                    story_position=1,
                )
            )
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="manuscript_revision",
                    source_ref="revision:r1",
                    title="Archive threshold",
                    content="Mira entered the archive and broke the brass seal.",
                    snowflake_step=10,
                    artifact_type="manuscript",
                    knowledge_class="observed",
                    scope="scene-1",
                    story_position=1,
                )
            )

            planning = wiki.retrieve_context(
                WikiContextQuery(
                    project_id="novel",
                    snowflake_step=9,
                    scope="scene-1",
                    story_position=1,
                    spoiler_horizon=1,
                )
            )
            drafting = wiki.retrieve_context(
                WikiContextQuery(
                    project_id="novel",
                    snowflake_step=10,
                    scope="scene-1",
                    story_position=1,
                    spoiler_horizon=1,
                )
            )

            planned_path = (
                Path(temp_dir)
                / "novel"
                / "modules"
                / "llm_wiki"
                / "sources"
                / "planned"
            )
            observed_path = (
                Path(temp_dir)
                / "novel"
                / "modules"
                / "llm_wiki"
                / "sources"
                / "observed"
            )
            self.assertTrue(any(planned_path.glob("*.json")))
            self.assertTrue(any(observed_path.glob("*.json")))
            self.assertEqual(
                {evidence.knowledge_class for evidence in planning.evidence},
                {"planned"},
            )
            self.assertEqual(
                {evidence.knowledge_class for evidence in drafting.evidence},
                {"planned", "observed"},
            )

    def test_local_backend_hides_superseded_and_future_observed_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="manuscript_revision",
                    source_ref="revision:r1",
                    title="Old archive scene",
                    content="Mira left the seal intact.",
                    snowflake_step=10,
                    artifact_type="manuscript",
                    knowledge_class="observed",
                    version=1,
                    scope="scene-1",
                    story_position=1,
                )
            )
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="manuscript_revision",
                    source_ref="revision:r2",
                    title="Revised archive scene",
                    content="Mira broke the brass seal.",
                    snowflake_step=10,
                    artifact_type="manuscript",
                    knowledge_class="observed",
                    version=2,
                    supersedes="revision:r1",
                    scope="scene-1",
                    story_position=1,
                )
            )
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="manuscript_revision",
                    source_ref="revision:r3",
                    title="Future scene",
                    content="Mira learns who altered the map.",
                    snowflake_step=10,
                    artifact_type="manuscript",
                    knowledge_class="observed",
                    version=1,
                    scope="scene-3",
                    story_position=3,
                )
            )

            result = wiki.retrieve_context(
                WikiContextQuery(
                    project_id="novel",
                    snowflake_step=10,
                    story_position=1,
                    spoiler_horizon=1,
                )
            )
            refs = {evidence.source_ref for evidence in result.evidence}

            self.assertNotIn("revision:r1", refs)
            self.assertIn("revision:r2", refs)
            self.assertNotIn("revision:r3", refs)

    def test_insights_are_advisory_and_reference_ingested_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:9:scene-1",
                    title="Archive scene expansion",
                    content="The brass seal is expected to break.",
                    snowflake_step=9,
                    artifact_type="expanded_scenes",
                    knowledge_class="planned",
                    scope="scene-1",
                    story_position=1,
                )
            )

            result = wiki.analyze(
                WikiInsightQuery(
                    project_id="novel",
                    snowflake_step=10,
                    scope="scene-1",
                    story_position=1,
                    spoiler_horizon=1,
                )
            )

            self.assertTrue(result.insights)
            self.assertTrue(result.insights[0].source_refs)
            self.assertEqual(result.insights[0].disposition, "advisory")


if __name__ == "__main__":
    unittest.main()
