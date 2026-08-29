from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import get_args
import unittest

import httpx
from pydantic import ValidationError

from app.integrations.knowledge_compiler import (
    NARRATIVE_CLP_CANDIDATE_ENTITY_TYPES,
    NARRATIVE_CLP_ENTITY_TYPES,
    NARRATIVE_CLP_PROFILE_NAME,
    NARRATIVE_CLP_PROFILE_VERSION,
    NARRATIVE_CLP_RELATION_TYPES,
    CandidateEntity,
    CandidateLifecycleChange,
    CandidateRelation,
    CompilerEvidence,
    KnowledgeCompiler,
    KnowledgeCompilerRequest,
    KnowledgeCompilerResult,
    build_revision_compiler_request,
    normalize_compiler_candidates,
)
from app.integrations.llmwiki_clp import (
    KnowledgeCompilerResponseError,
    KnowledgeCompilerTransportError,
    LlmWikiClpClient,
)
from app.data import SQLiteWritingDataStore
from app.models import (
    CanonEntity,
    ManuscriptProposalCreate,
    ManuscriptRevision,
    NarrativeRelation,
    ProjectCreate,
    SceneContractCreate,
    StoryThread,
    StoryThreadCreate,
    StoryThreadStatus,
)
from app.narrative.director import DirectorAnalyzer
from app.narrative.projector import NarrativeGraphProjector
from app.narrative.snapshot import NarrativeSnapshot
from app.outbox.handlers import OutboxJobContext, run_clp_extraction_job
from app.outbox.service import OutboxService


SOURCE_REF = "manuscript_revision:revision-1"


def _revision() -> ManuscriptRevision:
    return ManuscriptRevision(
        id="revision-1",
        project_id="project-1",
        scene_id="scene-1",
        proposal_id="proposal-1",
        title="The archive door",
        content="Mira suspects Rowan is hiding the archive key.",
        version=2,
        created_at="2026-08-29T08:00:00+00:00",
    )


def _request(*, compiler_version: str = "llmwiki-clp-test") -> KnowledgeCompilerRequest:
    return build_revision_compiler_request(
        revision=_revision(),
        scene_sequence=7,
        canon_entities=[
            CanonEntity(
                id="canon-character-mira",
                project_id="project-1",
                entity_type="character",
                name="Mira",
                version=3,
            )
        ],
        story_threads=[
            StoryThread(
                id="thread-key",
                project_id="project-1",
                thread_type="mystery",
                title="Who has the archive key?",
                status="developing",
            )
        ],
        narrative_relations=[
            NarrativeRelation(
                id="relation-1",
                project_id="project-1",
                source="character:Mira",
                target="character:Rowan",
                relation="SUSPECTS",
                valid_from=4,
                confidence=0.8,
                source_ref="manuscript_revision:revision-0",
            )
        ],
        compiler_version=compiler_version,
    )


def _evidence() -> list[CompilerEvidence]:
    return [
        CompilerEvidence(
            source_ref=SOURCE_REF,
            excerpt="Mira suspects Rowan is hiding the archive key.",
        )
    ]


def _valid_result(*, compiler_version: str = "llmwiki-clp-test") -> KnowledgeCompilerResult:
    return KnowledgeCompilerResult(
        project_id="project-1",
        revision_id="revision-1",
        source_ref=SOURCE_REF,
        profile_name=NARRATIVE_CLP_PROFILE_NAME,
        profile_version=NARRATIVE_CLP_PROFILE_VERSION,
        compiler_version=compiler_version,
        entity_candidates=[
            CandidateEntity(
                entity_type="Character",
                name="Rowan",
                summary="A keeper connected to the archive key.",
                confidence=0.78,
                source_ref=SOURCE_REF,
                evidence=_evidence(),
            )
        ],
        relation_candidates=[
            CandidateRelation(
                source="character:Mira",
                target="character:Rowan",
                relation="SUSPECTS",
                valid_from=7,
                valid_to=None,
                confidence=0.84,
                source_ref=SOURCE_REF,
                evidence=_evidence(),
            )
        ],
        lifecycle_candidates=[
            CandidateLifecycleChange(
                subject_type="StoryThread",
                subject_id="thread-key",
                from_state="developing",
                proposed_state="dormant",
                confidence=0.65,
                source_ref=SOURCE_REF,
                evidence=_evidence(),
            )
        ],
    )


class KnowledgeCompilerContractTests(unittest.TestCase):
    def test_port_is_application_owned_and_accepts_only_application_dtos(self) -> None:
        self.assertTrue(getattr(KnowledgeCompiler, "_is_protocol", False))
        annotations = KnowledgeCompiler.extract_revision.__annotations__
        self.assertIs(annotations["request"], KnowledgeCompilerRequest)
        self.assertIs(annotations["return"], KnowledgeCompilerResult)

    def test_revision_builds_explicit_sidecar_request_contract(self) -> None:
        request = _request()

        self.assertEqual(request.project_id, "project-1")
        self.assertEqual(request.revision_id, "revision-1")
        self.assertEqual(request.scene_id, "scene-1")
        self.assertEqual(request.scene_sequence, 7)
        self.assertEqual(request.source_ref, SOURCE_REF)
        self.assertEqual(request.revision_text, _revision().content)
        self.assertEqual(request.profile_name, NARRATIVE_CLP_PROFILE_NAME)
        self.assertEqual(request.profile_version, NARRATIVE_CLP_PROFILE_VERSION)
        self.assertEqual(request.compiler_version, "llmwiki-clp-test")
        self.assertEqual(request.context.entities[0].id, "canon-character-mira")
        self.assertEqual(request.context.story_threads[0].status, "developing")
        self.assertEqual(request.context.relations[0].relation, "SUSPECTS")
        self.assertEqual(
            request.domain_schema.story_thread_statuses,
            list(get_args(StoryThreadStatus)),
        )
        self.assertNotIn("archived", request.domain_schema.story_thread_statuses)

    def test_relation_candidate_preserves_temporal_provenance_fields(self) -> None:
        candidate = _valid_result().relation_candidates[0]

        self.assertEqual(candidate.source, "character:Mira")
        self.assertEqual(candidate.target, "character:Rowan")
        self.assertEqual(candidate.relation, "SUSPECTS")
        self.assertEqual(candidate.valid_from, 7)
        self.assertIsNone(candidate.valid_to)
        self.assertEqual(candidate.confidence, 0.84)
        self.assertEqual(candidate.source_ref, SOURCE_REF)
        self.assertEqual(candidate.evidence[0].source_ref, SOURCE_REF)
        self.assertIn("archive key", candidate.evidence[0].excerpt)

    def test_invalid_relation_or_lifecycle_state_is_rejected(self) -> None:
        relation = _valid_result().relation_candidates[0].model_dump()
        relation["relation"] = "EXECUTE_SQL"
        with self.assertRaises(ValidationError):
            CandidateRelation.model_validate(relation)

        lifecycle = _valid_result().lifecycle_candidates[0].model_dump()
        lifecycle["proposed_state"] = "archived"
        with self.assertRaises(ValidationError):
            CandidateLifecycleChange.model_validate(lifecycle)

    def test_candidates_normalize_to_existing_review_proposals_only(self) -> None:
        proposals = normalize_compiler_candidates(_valid_result())

        self.assertEqual(
            [proposal.target for proposal in proposals],
            ["canon_entity", "narrative_relation", "story_thread_status"],
        )
        self.assertTrue(all(proposal.source_ref == SOURCE_REF for proposal in proposals))
        relation = proposals[1]
        self.assertEqual(relation.action, "create")
        self.assertEqual(relation.payload["relation"], "SUSPECTS")
        self.assertEqual(relation.payload["evidence"][0]["source_ref"], SOURCE_REF)
        lifecycle = proposals[2]
        self.assertEqual(lifecycle.action, "update")
        self.assertEqual(lifecycle.target_record_id, "thread-key")
        self.assertEqual(lifecycle.payload["from_state"], "developing")
        self.assertEqual(lifecycle.payload["proposed_state"], "dormant")

    def test_candidate_schema_forbids_backend_actions_and_unknown_fields(self) -> None:
        payload = _valid_result().relation_candidates[0].model_dump()
        payload["sql"] = "DELETE FROM narrative_relations"
        with self.assertRaises(ValidationError):
            CandidateRelation.model_validate(payload)


class NarrativeClpProfileContractTests(unittest.TestCase):
    def test_profile_matches_python_domain_contract(self) -> None:
        path = (
            Path(__file__).parents[1]
            / "app"
            / "integrations"
            / "profiles"
            / "ai-writing-narrative.profile.json"
        )
        profile = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(profile["name"], NARRATIVE_CLP_PROFILE_NAME)
        self.assertEqual(profile["version"], NARRATIVE_CLP_PROFILE_VERSION)
        self.assertEqual(profile["entity_types"], list(NARRATIVE_CLP_ENTITY_TYPES))
        self.assertEqual(
            profile["candidate_entity_types"],
            list(NARRATIVE_CLP_CANDIDATE_ENTITY_TYPES),
        )
        self.assertEqual(profile["relation_types"], list(NARRATIVE_CLP_RELATION_TYPES))
        self.assertEqual(
            profile["story_thread"]["statuses"],
            list(get_args(StoryThreadStatus)),
        )
        self.assertNotIn("archived", profile["story_thread"]["statuses"])


class LlmWikiClpHttpAdapterTests(unittest.TestCase):
    def _client(self, handler, *, compiler_version: str = "llmwiki-clp-test") -> LlmWikiClpClient:
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        self.addCleanup(http_client.close)
        return LlmWikiClpClient(
            base_url="http://127.0.0.1:43117",
            timeout_seconds=0.25,
            compiler_version=compiler_version,
            http_client=http_client,
        )

    def test_http_adapter_posts_json_and_validates_response(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_valid_result().model_dump(mode="json"))

        result = self._client(handler).extract_revision(_request())

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/v1/extract-revision")
        self.assertEqual(captured["body"]["revision_id"], "revision-1")
        self.assertEqual(result.relation_candidates[0].relation, "SUSPECTS")

    def test_http_adapter_rejects_non_loopback_sidecar_urls(self) -> None:
        with self.assertRaises(ValueError):
            LlmWikiClpClient(
                base_url="https://compiler.example.com",
                compiler_version="llmwiki-clp-test",
            )

    def test_http_adapter_isolates_connection_timeout_and_server_errors(self) -> None:
        for raised in (
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("sidecar timed out"),
        ):
            with self.subTest(error=type(raised).__name__):

                def handler(request: httpx.Request, exc=raised) -> httpx.Response:
                    raise exc

                with self.assertRaises(KnowledgeCompilerTransportError):
                    self._client(handler).extract_revision(_request())

        def server_error(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "internal failure"})

        with self.assertRaises(KnowledgeCompilerTransportError):
            self._client(server_error).extract_revision(_request())

    def test_http_adapter_rejects_malformed_or_invalid_responses(self) -> None:
        def malformed(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not-json")

        with self.assertRaises(KnowledgeCompilerResponseError):
            self._client(malformed).extract_revision(_request())

        invalid = _valid_result().model_dump(mode="json")
        invalid["relation_candidates"][0]["relation"] = "DROP_TABLE"

        def invalid_candidate(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=invalid)

        with self.assertRaises(KnowledgeCompilerResponseError):
            self._client(invalid_candidate).extract_revision(_request())

    def test_http_adapter_rejects_response_identity_drift(self) -> None:
        mismatched = _valid_result().model_dump(mode="json")
        mismatched["project_id"] = "other-project"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=mismatched)

        with self.assertRaises(KnowledgeCompilerResponseError):
            self._client(handler).extract_revision(_request())


class RecordingCompiler:
    compiler_version = "llmwiki-clp-test"

    def __init__(self, *, thread_id: str, fail: Exception | None = None) -> None:
        self.thread_id = thread_id
        self.fail = fail
        self.calls = 0

    def extract_revision(self, request: KnowledgeCompilerRequest) -> KnowledgeCompilerResult:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        evidence = [
            CompilerEvidence(
                source_ref=request.source_ref,
                excerpt="Mira suspects Rowan is hiding the archive key.",
            )
        ]
        return KnowledgeCompilerResult(
            project_id=request.project_id,
            revision_id=request.revision_id,
            source_ref=request.source_ref,
            profile_name=request.profile_name,
            profile_version=request.profile_version,
            compiler_version=request.compiler_version,
            relation_candidates=[
                CandidateRelation(
                    source="character:Mira",
                    target="character:Rowan",
                    relation="SUSPECTS",
                    valid_from=request.scene_sequence,
                    confidence=0.84,
                    source_ref=request.source_ref,
                    evidence=evidence,
                )
            ],
            lifecycle_candidates=[
                CandidateLifecycleChange(
                    subject_id=self.thread_id,
                    from_state="developing",
                    proposed_state="dormant",
                    confidence=0.65,
                    source_ref=request.source_ref,
                    evidence=evidence,
                )
            ],
        )


class NoopWiki:
    def ingest(self, document):
        return None

    def retrieve_context(self, query):
        raise AssertionError("not used")

    def analyze(self, query):
        raise AssertionError("not used")


def _accepted_revision_store(temp_dir: str):
    store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
    store.init()
    project = store.create_project(
        ProjectCreate(title="CLP Novel", premise="Candidates need review.")
    )
    scene = store.create_scene_contract(
        project.id,
        SceneContractCreate(
            sequence=1,
            title="The archive door",
            pov="Mira",
            goal="Learn who has the key.",
        ),
    )
    thread = store.create_story_thread(
        project.id,
        StoryThreadCreate(
            thread_type="mystery",
            title="Who has the archive key?",
            status="developing",
        ),
    )
    proposal = store.create_manuscript_proposal(
        project.id,
        ManuscriptProposalCreate(
            scene_id=scene.id,
            title="The archive door",
            content="Mira suspects Rowan is hiding the archive key.",
        ),
    )
    accepted = store.accept_manuscript_proposal(project.id, proposal.id)
    assert accepted is not None
    revision = store.list_manuscript_revisions(project.id)[0]
    return store, project.id, scene.id, thread.id, revision


class ClpPostAcceptPipelineTests(unittest.TestCase):
    def test_acceptance_enqueues_clp_without_coupling_commit_to_sidecar(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, _, _, revision = _accepted_revision_store(temp_dir)

            jobs = store.list_outbox_jobs(project_id)
            revision_count = len(store.list_manuscript_revisions(project_id))

        self.assertEqual(revision_count, 1)
        self.assertIn("clp_extraction", [job.job_type for job in jobs])
        clp_job = next(job for job in jobs if job.job_type == "clp_extraction")
        self.assertEqual(clp_job.aggregate_id, revision.id)
        self.assertEqual(clp_job.payload["source_ref"], f"manuscript_revision:{revision.id}")

    def test_successful_clp_analysis_replays_without_second_sidecar_call(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, _, thread_id, _ = _accepted_revision_store(temp_dir)
            compiler = RecordingCompiler(thread_id=thread_id)
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            context = OutboxJobContext(wiki=NoopWiki(), data_store=store, compiler=compiler)

            first = run_clp_extraction_job(context, job.payload)
            second = run_clp_extraction_job(context, job.payload)
            clp_proposals = [
                item
                for item in store.list_writeback_proposals(project_id)
                if item.target in {"narrative_relation", "story_thread_status"}
            ]

        self.assertEqual(compiler.calls, 1)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(clp_proposals), 2)
        self.assertTrue(all(item.status == "pending_review" for item in clp_proposals))

    def test_successful_zero_candidate_result_is_cached_without_second_sidecar_call(self) -> None:
        class EmptyCompiler:
            compiler_version = "llmwiki-clp-empty"

            def __init__(self) -> None:
                self.calls = 0

            def extract_revision(
                self, request: KnowledgeCompilerRequest
            ) -> KnowledgeCompilerResult:
                self.calls += 1
                return KnowledgeCompilerResult(
                    project_id=request.project_id,
                    revision_id=request.revision_id,
                    source_ref=request.source_ref,
                    profile_name=request.profile_name,
                    profile_version=request.profile_version,
                    compiler_version=request.compiler_version,
                )

        with TemporaryDirectory() as temp_dir:
            store, project_id, _, _, _ = _accepted_revision_store(temp_dir)
            compiler = EmptyCompiler()
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            context = OutboxJobContext(wiki=NoopWiki(), data_store=store, compiler=compiler)

            first = run_clp_extraction_job(context, job.payload)
            second = run_clp_extraction_job(context, job.payload)

        self.assertEqual(compiler.calls, 1)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.result_json["proposal_ids"], [])

    def test_pending_candidates_do_not_pollute_graph_snapshot_or_director(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, scene_id, thread_id, _ = _accepted_revision_store(temp_dir)
            before_graph = NarrativeGraphProjector(store).project(project_id)
            before_snapshot = NarrativeSnapshot.for_scene(
                project_id=project_id, scene_id=scene_id, data_store=store
            )
            before_director = DirectorAnalyzer(store).for_scene(
                project_id=project_id, scene_id=scene_id
            )
            compiler = RecordingCompiler(thread_id=thread_id)
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            run_clp_extraction_job(
                OutboxJobContext(wiki=NoopWiki(), data_store=store, compiler=compiler),
                job.payload,
            )

            after_graph = NarrativeGraphProjector(store).project(project_id)
            after_snapshot = NarrativeSnapshot.for_scene(
                project_id=project_id, scene_id=scene_id, data_store=store
            )
            after_director = DirectorAnalyzer(store).for_scene(
                project_id=project_id, scene_id=scene_id
            )
            thread_status = store.list_story_threads(project_id)[0].status

        self.assertEqual(
            before_graph.networkx.number_of_edges(), after_graph.networkx.number_of_edges()
        )
        self.assertEqual(before_snapshot.narrative_relations, after_snapshot.narrative_relations)
        self.assertEqual(before_director, after_director)
        self.assertEqual(thread_status, "developing")

    def test_author_accept_is_the_only_path_that_applies_relation_and_lifecycle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, _, thread_id, _ = _accepted_revision_store(temp_dir)
            compiler = RecordingCompiler(thread_id=thread_id)
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            run_clp_extraction_job(
                OutboxJobContext(wiki=NoopWiki(), data_store=store, compiler=compiler),
                job.payload,
            )
            proposals = store.list_writeback_proposals(project_id)
            relation = next(item for item in proposals if item.target == "narrative_relation")
            lifecycle = next(item for item in proposals if item.target == "story_thread_status")

            self.assertEqual(store.list_narrative_relations(project_id), [])
            self.assertEqual(store.list_story_threads(project_id)[0].status, "developing")

            accepted_relation = store.update_writeback_proposal_status(
                project_id, relation.id, "accepted"
            )
            accepted_lifecycle = store.update_writeback_proposal_status(
                project_id, lifecycle.id, "accepted"
            )
            relation_count = len(store.list_narrative_relations(project_id))
            thread_status = store.list_story_threads(project_id)[0].status

        self.assertEqual(accepted_relation.status, "accepted")
        self.assertEqual(accepted_lifecycle.status, "accepted")
        self.assertEqual(relation_count, 1)
        self.assertEqual(thread_status, "dormant")

    def test_rejected_clp_candidates_do_not_change_narrative_domain(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, _, thread_id, _ = _accepted_revision_store(temp_dir)
            compiler = RecordingCompiler(thread_id=thread_id)
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            run_clp_extraction_job(
                OutboxJobContext(wiki=NoopWiki(), data_store=store, compiler=compiler),
                job.payload,
            )
            proposals = store.list_writeback_proposals(project_id)
            relation = next(item for item in proposals if item.target == "narrative_relation")
            lifecycle = next(item for item in proposals if item.target == "story_thread_status")

            rejected_relation = store.update_writeback_proposal_status(
                project_id, relation.id, "rejected"
            )
            rejected_lifecycle = store.update_writeback_proposal_status(
                project_id, lifecycle.id, "rejected"
            )
            relation_count = len(store.list_narrative_relations(project_id))
            thread_status = store.list_story_threads(project_id)[0].status

        self.assertEqual(rejected_relation.status, "rejected")
        self.assertEqual(rejected_lifecycle.status, "rejected")
        self.assertEqual(relation_count, 0)
        self.assertEqual(thread_status, "developing")

    def test_retry_failed_clp_job_creates_one_proposal_set(self) -> None:
        class FlakyCompiler(RecordingCompiler):
            def extract_revision(
                self, request: KnowledgeCompilerRequest
            ) -> KnowledgeCompilerResult:
                if self.calls == 0:
                    self.calls += 1
                    raise KnowledgeCompilerTransportError("temporary timeout")
                return super().extract_revision(request)

        with TemporaryDirectory() as temp_dir:
            store, project_id, _, thread_id, _ = _accepted_revision_store(temp_dir)
            compiler = FlakyCompiler(thread_id=thread_id)
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            service = OutboxService(data_store=store, wiki=NoopWiki(), compiler=compiler)

            first = service.process_job(project_id, job.id)
            retried = service.retry(project_id, job.id)
            proposals = [
                item
                for item in store.list_writeback_proposals(project_id)
                if item.target in {"narrative_relation", "story_thread_status"}
            ]

        self.assertEqual(first.status, "failed")
        self.assertEqual(retried.status, "succeeded")
        self.assertEqual(compiler.calls, 2)
        self.assertEqual(len(proposals), 2)

    def test_sidecar_failure_marks_only_clp_job_failed_and_revision_survives(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, project_id, _, thread_id, revision = _accepted_revision_store(temp_dir)
            compiler = RecordingCompiler(
                thread_id=thread_id,
                fail=KnowledgeCompilerTransportError("connection refused"),
            )
            job = next(
                item
                for item in store.list_outbox_jobs(project_id)
                if item.job_type == "clp_extraction"
            )
            service = OutboxService(data_store=store, wiki=NoopWiki(), compiler=compiler)

            failed = service.process_job(project_id, job.id)
            saved_revision = store.get_manuscript_revision(project_id, revision.id)
            relation_count = len(store.list_narrative_relations(project_id))
            thread_status = store.list_story_threads(project_id)[0].status

        self.assertEqual(failed.status, "failed")
        self.assertIn("KnowledgeCompilerTransportError", failed.last_error)
        self.assertEqual(saved_revision.content, revision.content)
        self.assertEqual(relation_count, 0)
        self.assertEqual(thread_status, "developing")


if __name__ == "__main__":
    unittest.main()
