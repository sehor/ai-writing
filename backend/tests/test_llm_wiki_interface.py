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

            planned_path = Path(temp_dir) / "novel" / "modules" / "llm_wiki" / "sources" / "planned"
            observed_path = (
                Path(temp_dir) / "novel" / "modules" / "llm_wiki" / "sources" / "observed"
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

    def test_ingest_writes_readable_markdown_source_mirror(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1",
                    title="Story promise",
                    content="Mira must map the archive before it erases her.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                )
            )

            markdown_dir = Path(temp_dir) / "novel" / "modules" / "llm_wiki" / "sources" / "planned"
            markdown_files = list(markdown_dir.glob("*.md"))
            self.assertEqual(len(markdown_files), 1)
            markdown_path = markdown_files[0]
            self.assertTrue(markdown_path.is_file())
            content = markdown_path.read_text(encoding="utf-8")
            self.assertIn('title: "Story promise"', content)
            self.assertIn('source_ref: "snowflake:1"', content)
            self.assertIn("Mira must map the archive", content)

    def test_ingest_rebuilds_compiler_like_concept_projection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1",
                    title="Story promise",
                    content="Mira must map the archive before it erases her.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                )
            )

            concepts_dir = Path(temp_dir) / "novel" / "modules" / "llm_wiki" / "wiki" / "concepts"
            pages = list(concepts_dir.glob("*.md"))
            self.assertEqual(len(pages), 1)
            content = pages[0].read_text(encoding="utf-8")
            self.assertIn('title: "Story promise"', content)
            self.assertIn('kind: "concept"', content)
            self.assertIn('sources: ["snowflake:1"]', content)
            self.assertIn("Mira must map the archive", content)

    def test_projection_index_lists_only_active_approved_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1:old",
                    title="Old promise",
                    content="Mira leaves the archive sealed.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                )
            )
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1:new",
                    title="New promise",
                    content="Mira breaks the archive seal.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                    supersedes="snowflake:1:old",
                )
            )
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:2:draft",
                    title="Draft plot seed",
                    content="This draft should not become active projected knowledge.",
                    snowflake_step=2,
                    artifact_type="plot_seed",
                    knowledge_class="planned",
                    status="draft",
                )
            )

            project_path = Path(temp_dir) / "novel" / "modules" / "llm_wiki"
            index = (project_path / "wiki" / "index.md").read_text(encoding="utf-8")
            concept_pages = list((project_path / "wiki" / "concepts").glob("*.md"))

            self.assertIn("New promise", index)
            self.assertNotIn("Old promise", index)
            self.assertNotIn("Draft plot seed", index)
            self.assertEqual(len(concept_pages), 1)

    def test_context_ranks_instruction_matches_before_merely_visible_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1:archive",
                    title="Archive promise",
                    content="Mira must map the archive before it erases her.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                )
            )
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1:market",
                    title="Market promise",
                    content="The market guild hides a counterfeit coin trail.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                )
            )

            result = wiki.retrieve_context(
                WikiContextQuery(
                    project_id="novel",
                    snowflake_step=2,
                    instruction="Expand the market guild and coin trail.",
                )
            )

            self.assertGreaterEqual(len(result.evidence), 2)
            self.assertEqual(result.evidence[0].source_ref, "snowflake:1:market")

    def test_context_evidence_uses_projection_style_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))
            wiki.ingest(
                WikiSourceDocument(
                    project_id="novel",
                    source_kind="snowflake_artifact",
                    source_ref="snowflake:1",
                    title="Story promise",
                    content="Mira maps the archive.\n\nThe archive erases uncommitted names.",
                    snowflake_step=1,
                    artifact_type="story_contract",
                    knowledge_class="planned",
                )
            )

            result = wiki.retrieve_context(WikiContextQuery(project_id="novel", snowflake_step=2))

            self.assertEqual(
                result.evidence[0].excerpt,
                "Mira maps the archive. The archive erases uncommitted names.",
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

    def test_insights_report_gap_when_no_stage_visible_evidence_exists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wiki = LocalFileLlmWiki(Path(temp_dir))

            result = wiki.analyze(
                WikiInsightQuery(
                    project_id="novel",
                    snowflake_step=4,
                    instruction="Find causal setup for the plot synopsis.",
                )
            )

            self.assertEqual(len(result.insights), 1)
            self.assertEqual(result.insights[0].kind, "stage_context_gap")
            self.assertEqual(result.insights[0].source_refs, [])


if __name__ == "__main__":
    unittest.main()
