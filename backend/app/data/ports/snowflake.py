from __future__ import annotations

from typing import Protocol

from app.models import (
    CanonEntity,
    ManuscriptProposal,
    ManuscriptRevision,
    SceneContract,
    SnowflakeArtifact,
    SnowflakeArtifactHead,
    SnowflakeArtifactRevision,
    SnowflakeArtifactRevisionCreate,
    SnowflakeRecordDecisionResponse,
    SnowflakeRecordRevision,
    SnowflakeRecordRevisionCreate,
    StoryThread,
)


class SnowflakeDataPort(Protocol):
    def create_snowflake_record_revision(
        self, project_id: str, create: SnowflakeRecordRevisionCreate, *, status: str = "draft"
    ) -> SnowflakeRecordRevision: ...

    def create_snowflake_record_revisions(
        self,
        project_id: str,
        creates: list[SnowflakeRecordRevisionCreate],
        *,
        status: str = "draft",
    ) -> list[SnowflakeRecordRevision]: ...

    def create_snowflake_revision(
        self,
        project_id: str,
        create: SnowflakeArtifactRevisionCreate,
        *,
        status: str | None = None,
        source: str | None = None,
    ) -> SnowflakeArtifactRevision: ...

    def decide_snowflake_record_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        decision: str,
        expected_revision_id: str,
        review_reason: str = "",
    ) -> SnowflakeRecordDecisionResponse: ...

    def decide_snowflake_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        decision: str,
        expected_head_revision_id: str,
        review_reason: str = "",
    ) -> tuple[SnowflakeArtifactRevision, SnowflakeArtifactHead, list[int], str]: ...

    def get_snowflake_artifact(
        self, project_id: str, step_number: int
    ) -> SnowflakeArtifact | None: ...

    def get_snowflake_record_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeRecordRevision | None: ...

    def get_snowflake_records(
        self, project_id: str, step_number: int, record_ids: list[str]
    ) -> list[SnowflakeRecordRevision]: ...

    def get_snowflake_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeArtifactRevision | None: ...

    def list_accepted_snowflake_records(
        self, project_id: str, step_number: int
    ) -> list[SnowflakeRecordRevision]: ...

    def list_canon_entities(self, project_id: str) -> list[CanonEntity]: ...

    def list_manuscript_proposals(self, project_id: str) -> list[ManuscriptProposal]: ...

    def list_manuscript_revisions(self, project_id: str) -> list[ManuscriptRevision]: ...

    def list_scene_contracts(self, project_id: str) -> list[SceneContract]: ...

    def list_snowflake_artifacts(self, project_id: str) -> list[SnowflakeArtifact]: ...

    def list_snowflake_heads(self, project_id: str) -> list[SnowflakeArtifactHead]: ...

    def list_snowflake_record_revisions(
        self, project_id: str, step_number: int, record_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[SnowflakeRecordRevision], int]: ...

    def list_snowflake_records(
        self, project_id: str, step_number: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[SnowflakeRecordRevision], int]: ...

    def list_snowflake_revisions(
        self, project_id: str, step_number: int, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[SnowflakeArtifactRevision], int]: ...

    def list_story_threads(self, project_id: str) -> list[StoryThread]: ...

    def patch_snowflake_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        content: str | None,
        structured_payload: dict | None,
    ) -> SnowflakeArtifactRevision | None: ...

    def skip_snowflake_step(self, project_id: str, step_number: int) -> SnowflakeArtifactHead: ...

    def snowflake_pending_counts(self, project_id: str) -> dict[int, int]: ...
