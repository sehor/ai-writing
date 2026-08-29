"""Payload builders and execution handlers for outbox jobs.

Payload builders turn domain records into plain JSON-safe dicts so the data
layer never depends on the LLM Wiki port directly. Handlers reconstruct the
port objects at execution time from an OutboxJobContext.

Import-cycle note: this module is imported by app.data.mixins.outbox while
app.data is still initialising, so module-level imports here must never
reach back into app.data (or anything that imports it, such as
app.analysis.service or app.cognition.snapshots). The analysis handlers
therefore import those lazily inside the function body; by the time a job
executes, every package is fully initialised.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

from app.llm_wiki.interfaces import (
    LlmWiki,
    WikiIngestionResult,
    WikiSourceDocument,
)
from app.models import ManuscriptRevision, SnowflakeArtifact

if TYPE_CHECKING:
    from app.cognition.registry import CognitionRegistry
    from app.data.interfaces import WritingDataStore


@dataclass
class OutboxJobContext:
    """Execution-time ports handed to every outbox handler."""

    wiki: LlmWiki
    data_store: "WritingDataStore"
    cognition: "CognitionRegistry | None" = None


def snowflake_index_payload(artifact: SnowflakeArtifact) -> dict:
    is_manuscript_draft = artifact.step_number == 10
    return {
        "project_id": artifact.project_id,
        "source_kind": "snowflake_artifact",
        "source_ref": f"snowflake:{artifact.step_number}",
        "title": f"Snowflake step {artifact.step_number}: {artifact.artifact}",
        "content": artifact.content,
        "snowflake_step": artifact.step_number,
        "artifact_type": artifact.artifact,
        "knowledge_class": "observed" if is_manuscript_draft else "planned",
        "status": "draft" if is_manuscript_draft else "approved",
    }


def manuscript_revision_index_payload(
    latest: ManuscriptRevision,
    previous_revision_id: str | None,
    story_position: int | None,
) -> dict:
    return {
        "project_id": latest.project_id,
        "source_kind": "manuscript_revision",
        "source_ref": f"manuscript_revision:{latest.id}",
        "title": latest.title,
        "content": latest.content,
        "snowflake_step": 10,
        "artifact_type": "manuscript",
        "knowledge_class": "observed",
        "version": latest.version,
        "supersedes": (
            f"manuscript_revision:{previous_revision_id}" if previous_revision_id else ""
        ),
        "scope": latest.scene_id,
        "story_position": story_position,
    }


def manuscript_revision_analysis_payload(revision: ManuscriptRevision) -> dict:
    """Shared payload for the post-acceptance analysis jobs (P1-07)."""
    return {
        "project_id": revision.project_id,
        "revision_id": revision.id,
        "source_ref": f"manuscript_revision:{revision.id}",
    }


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


OutboxHandler = Callable[[OutboxJobContext, dict], Any]

OUTBOX_HANDLERS: dict[str, OutboxHandler] = {
    "llm_wiki_ingest": run_llm_wiki_ingest,
    "consistency_analysis": run_consistency_analysis_job,
    "writeback_analysis": run_writeback_analysis_job,
}
