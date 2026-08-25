"""Payload builders and execution handlers for outbox jobs.

Payload builders turn domain records into plain JSON-safe dicts so the data
layer never depends on the LLM Wiki port directly. Handlers reconstruct the
port objects at execution time.
"""

from typing import Callable

from pydantic import ValidationError

from app.llm_wiki.interfaces import (
    LlmWiki,
    WikiIngestionResult,
    WikiSourceDocument,
)
from app.models import ManuscriptRevision, SnowflakeArtifact


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


def run_llm_wiki_ingest(wiki: LlmWiki, payload: dict) -> WikiIngestionResult:
    try:
        document = WikiSourceDocument.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid wiki ingest payload: {exc}") from exc
    result = wiki.ingest(document)
    if not isinstance(result, WikiIngestionResult):
        raise TypeError("LLM Wiki ingest returned an unexpected result type.")
    return result


OutboxHandler = Callable[[LlmWiki, dict], object]

OUTBOX_HANDLERS: dict[str, OutboxHandler] = {
    "llm_wiki_ingest": run_llm_wiki_ingest,
}
