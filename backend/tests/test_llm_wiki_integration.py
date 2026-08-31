from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.agents.writing_workflow import LocalDraftWritingWorkflow
from app.data import SQLiteWritingDataStore, get_data_store
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import (
    WikiContextQuery,
    WikiContextResult,
    WikiEvidence,
    WikiIngestionResult,
    WikiInsight,
    WikiInsightQuery,
    WikiInsightResult,
    WikiSourceDocument,
)
from app.main import app
from app.models import SnowflakeArtifact
from app.routers.snowflake import (
    SNOWFLAKE_STEPS,
    get_writing_workflow,
    snowflake_wiki_document,
)
from _polling import wait_until


class RecordingLlmWiki:
    def __init__(self) -> None:
        self.documents: list[WikiSourceDocument] = []
        self.context_queries: list[WikiContextQuery] = []
        self.insight_queries: list[WikiInsightQuery] = []

    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        self.documents.append(document)
        return WikiIngestionResult(status="stored", source_ref=document.source_ref)

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        self.context_queries.append(query)
        return WikiContextResult(
            summary="recorded",
            evidence=[
                WikiEvidence(
                    source_ref="wiki:test-evidence",
                    title="Recorded evidence",
                    excerpt="A stage-aware constraint from the independent wiki.",
                    knowledge_class="planned",
                    snowflake_step=max(1, query.snowflake_step - 1),
                )
            ],
            constraints=[],
        )

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        self.insight_queries.append(query)
        return WikiInsightResult(
            summary="recorded",
            insights=[
                WikiInsight(
                    kind="recorded",
                    summary="Recorded insight",
                    detail="The interface call reached the configured backend.",
                    source_refs=["wiki:test-evidence"],
                )
            ],
        )


class LlmWikiIntegrationTests(unittest.TestCase):
    def test_unconfirmed_step_ten_artifact_is_not_approved_knowledge(self) -> None:
        document = snowflake_wiki_document(
            SnowflakeArtifact(
                project_id="novel",
                step_number=10,
                artifact="manuscript",
                content="A draft that has not been accepted.",
            )
        )

        self.assertEqual(document.knowledge_class, "observed")
        self.assertEqual(document.status, "draft")

    def test_snowflake_and_manuscript_flows_use_only_the_llm_wiki_port(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            wiki = RecordingLlmWiki()
            app.dependency_overrides[get_data_store] = lambda: store
            app.dependency_overrides[get_llm_wiki] = lambda: wiki
            app.dependency_overrides[get_writing_workflow] = lambda: LocalDraftWritingWorkflow(
                store,
                SNOWFLAKE_STEPS,
                wiki,
            )
            try:
                with TestClient(app) as client:
                    project_response = client.post(
                        "/api/projects",
                        json={
                            "title": "Wiki Port",
                            "premise": "A city changes when its archive is read.",
                        },
                    )
                    self.assertEqual(project_response.status_code, 201)
                    project_id = project_response.json()["id"]

                    saved_response = client.put(
                        f"/api/projects/{project_id}/snowflake/artifacts/1",
                        json={"content": "Mira must map the archive before it erases her."},
                    )
                    self.assertEqual(saved_response.status_code, 200)

                    generated_response = client.post(
                        "/api/snowflake/generate",
                        json={
                            "project_id": project_id,
                            "step_number": 2,
                            "user_input": "Expand the promise into three disasters and an ending.",
                        },
                    )
                    self.assertEqual(generated_response.status_code, 200)
                    self.assertIn("LLM Wiki Context", generated_response.json()["content"])

                    scene_response = client.post(
                        f"/api/projects/{project_id}/scene-contracts",
                        json={
                            "sequence": 1,
                            "title": "Archive Threshold",
                            "pov": "Mira",
                            "goal": "Enter the archive.",
                            "conflict": "The map refuses the door.",
                            "turning_point": "The map redraws itself.",
                            "source_artifact_step": 8,
                        },
                    )
                    self.assertEqual(scene_response.status_code, 201)
                    scene = scene_response.json()

                    proposal_response = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    )
                    self.assertEqual(proposal_response.status_code, 201)
                    proposal = proposal_response.json()

                    accepted_response = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
                        json={"status": "accepted"},
                    )
                    self.assertEqual(accepted_response.status_code, 200)

                    context_response = client.post(
                        f"/api/projects/{project_id}/wiki/context",
                        json={
                            "project_id": project_id,
                            "snowflake_step": 10,
                            "scope": scene["id"],
                            "story_position": 1,
                            "spoiler_horizon": 1,
                        },
                    )
                    self.assertEqual(context_response.status_code, 200)

                    insight_response = client.post(
                        f"/api/projects/{project_id}/wiki/insights",
                        json={
                            "project_id": project_id,
                            "snowflake_step": 10,
                            "scope": scene["id"],
                            "story_position": 1,
                            "spoiler_horizon": 1,
                        },
                    )
                    self.assertEqual(insight_response.status_code, 200)

                    # P1-03: handlers run in the background dispatcher, so the
                    # ingested documents are only complete once every job has
                    # settled. Wait before leaving the app (and its loop).
                    wait_until(
                        lambda: all(
                            job.status == "succeeded" for job in store.list_outbox_jobs(project_id)
                        ),
                        timeout_seconds=20,
                        message="all scheduled wiki index jobs to settle",
                    )
            finally:
                app.dependency_overrides.clear()

        planned = [document for document in wiki.documents if document.knowledge_class == "planned"]
        observed = [
            document for document in wiki.documents if document.knowledge_class == "observed"
        ]
        self.assertEqual({document.snowflake_step for document in planned}, {1, 2})
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0].source_kind, "manuscript_revision")
        self.assertEqual(observed[0].snowflake_step, 10)
        self.assertEqual(observed[0].story_position, 1)
        self.assertTrue(any(query.snowflake_step == 2 for query in wiki.context_queries))
        self.assertTrue(any(query.snowflake_step == 10 for query in wiki.context_queries))
        self.assertEqual(wiki.insight_queries[-1].project_id, observed[0].project_id)

        forbidden_attribute_names = {
            "snapshot",
            "canon_entities",
            "memory_records",
            "cognition",
            "settings",
            "data_store",
        }
        for call in [*wiki.documents, *wiki.context_queries, *wiki.insight_queries]:
            self.assertTrue(forbidden_attribute_names.isdisjoint(call.model_fields))


if __name__ == "__main__":
    unittest.main()
