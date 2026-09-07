"""Pure JSON event contracts shared by transactions and execution adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def manuscript_revision_analysis_payload(revision: ManuscriptRevision) -> dict:
    """Shared payload for the post-acceptance analysis jobs (P1-07)."""
    return {
        "project_id": revision.project_id,
        "revision_id": revision.id,
        "source_ref": f"manuscript_revision:{revision.id}",
    }
