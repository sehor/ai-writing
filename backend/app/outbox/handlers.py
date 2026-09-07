"""Execution handlers for outbox jobs; payload contracts live in app.outbox.events."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

from app.llm_wiki.interfaces import (
    LlmWiki,
    WikiIngestionResult,
    WikiSourceDocument,
)
from app.models import ManuscriptRevision

# Compatibility exports point to the same pure factories used by transactions.
from app.outbox.events import (
    snowflake_index_payload as snowflake_index_payload,
    manuscript_revision_index_payload as manuscript_revision_index_payload,
    manuscript_revision_analysis_payload as manuscript_revision_analysis_payload,
)

if TYPE_CHECKING:
    from app.cognition.registry import CognitionRegistry
    from app.data.interfaces import WritingDataStore
    from app.integrations.knowledge_compiler import KnowledgeCompiler


@dataclass
class OutboxJobContext:
    """Execution-time ports handed to every outbox handler."""

    wiki: LlmWiki
    data_store: "WritingDataStore"
    cognition: "CognitionRegistry | None" = None
    compiler: "KnowledgeCompiler | None" = None


def run_llm_wiki_ingest(context: OutboxJobContext, payload: dict) -> WikiIngestionResult:
    try:
        document = WikiSourceDocument.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid wiki ingest payload: {exc}") from exc
    result = context.wiki.ingest(document)
    if not isinstance(result, WikiIngestionResult):
        raise TypeError("LLM Wiki ingest returned an unexpected result type.")
    return result


def _revision_from_payload(context: OutboxJobContext, payload: dict) -> ManuscriptRevision:
    project_id = str(payload.get("project_id", ""))
    revision_id = str(payload.get("revision_id", ""))
    revision = context.data_store.get_manuscript_revision(project_id, revision_id)
    if revision is None:
        raise ValueError(
            f"Manuscript revision {revision_id!r} does not exist in project {project_id!r}."
        )
    return revision


def run_consistency_analysis_job(context: OutboxJobContext, payload: dict) -> object:
    """Produce the consistency report for one revision without a manual trigger.

    The check runs through AnalysisService, so unchanged inputs replay the
    stored run instead of duplicating analysis_runs rows.
    """
    # Lazy imports: see the import-cycle note at module top.
    from app.analysis.consistency import build_consistency_fingerprint, check_revision
    from app.analysis.service import AnalysisService
    from app.cognition.snapshots import NarrativeSnapshot

    revision = _revision_from_payload(context, payload)
    snapshot = NarrativeSnapshot.for_scene(
        project_id=revision.project_id,
        scene_id=revision.scene_id,
        data_store=context.data_store,
    )
    outcome = AnalysisService(data_store=context.data_store).run_consistency_analysis(
        project_id=revision.project_id,
        source_ref=str(payload.get("source_ref") or f"manuscript_revision:{revision.id}"),
        fingerprint=build_consistency_fingerprint(
            revision,
            snapshot.scene,
            snapshot.canon_entities,
            snapshot.world_truth,
        ),
        check=lambda: check_revision(
            revision,
            snapshot.scene,
            snapshot.canon_entities,
            snapshot.world_truth,
        ),
    )
    return outcome.run


def run_writeback_analysis_job(context: OutboxJobContext, payload: dict) -> object:
    """Pre-create deterministic write-back proposals for human review.

    Proposals land in pending_review only; nothing is auto-accepted. The
    generation path and processor name match POST .../writeback/proposals/from-revision,
    so provider-backed processors can join later behind the same interface.
    """
    # Lazy imports: see the import-cycle note at module top.
    from app.analysis.service import AnalysisService, writeback_input_fingerprint
    from app.cognition.interfaces import CommittedContentEvent
    from app.cognition.registry import get_cognition_registry
    from app.cognition.snapshots import build_project_snapshot

    revision = _revision_from_payload(context, payload)
    cognition = context.cognition or get_cognition_registry()
    snapshot = build_project_snapshot(revision.project_id, context.data_store)

    def _generate() -> list:
        reports = cognition.ingest_committed_content(
            snapshot,
            CommittedContentEvent(
                source="manuscript_revision",
                source_ref=f"manuscript_revision:{revision.id}",
                title=revision.title,
                content=revision.content,
                revision=revision,
            ),
        )
        return [proposal for report in reports for proposal in report.writeback_proposals]

    outcome = AnalysisService(data_store=context.data_store).run_writeback_generation(
        project_id=revision.project_id,
        source_ref=str(payload.get("source_ref") or f"manuscript_revision:{revision.id}"),
        processor=str(payload.get("processor") or "local_writeback"),
        fingerprint=writeback_input_fingerprint(
            revision,
            canon_entities=snapshot.canon_entities,
            memory_records=snapshot.memory_records,
        ),
        generate=_generate,
    )
    return outcome.run


def run_clp_extraction_job(context: OutboxJobContext, payload: dict) -> object:
    """Compile one accepted revision into reviewable Narrative candidates.

    The sidecar is invoked only inside AnalysisService's generation callback.
    A succeeded input hash therefore replays stored proposal ids without a
    second compiler call, while failures are recorded and remain retryable.
    """
    from app.analysis.service import AnalysisService
    from app.integrations.knowledge_compiler import (
        DisabledKnowledgeCompiler,
        build_revision_compiler_request,
        normalize_compiler_candidates,
    )

    revision = _revision_from_payload(context, payload)
    scene = context.data_store.get_scene_contract(revision.project_id, revision.scene_id)
    if scene is None:
        raise ValueError("Scene contract not found for accepted manuscript revision.")
    compiler = context.compiler or DisabledKnowledgeCompiler()
    request = build_revision_compiler_request(
        revision=revision,
        scene_sequence=scene.sequence,
        canon_entities=context.data_store.list_canon_entities(revision.project_id),
        story_threads=context.data_store.list_story_threads(revision.project_id),
        narrative_relations=context.data_store.list_narrative_relations(revision.project_id),
        compiler_version=compiler.compiler_version,
    )

    def _generate() -> list:
        result = compiler.extract_revision(request)
        return normalize_compiler_candidates(result)

    outcome = AnalysisService(data_store=context.data_store).run_writeback_generation(
        project_id=revision.project_id,
        source_ref=request.source_ref,
        processor="llmwiki_clp",
        fingerprint=request.model_dump(mode="json"),
        generate=_generate,
    )
    return outcome.run


OutboxHandler = Callable[[OutboxJobContext, dict], Any]

OUTBOX_HANDLERS: dict[str, OutboxHandler] = {
    "llm_wiki_ingest": run_llm_wiki_ingest,
    "consistency_analysis": run_consistency_analysis_job,
    "writeback_analysis": run_writeback_analysis_job,
    "clp_extraction": run_clp_extraction_job,
}
