from pathlib import Path
from re import sub
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import sqlite3
from typing import Iterator, Protocol

from app.models import (
    CanonEntity,
    CanonEntityCreate,
    CanonEntityUpdate,
    MemoryRecord,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    ProjectCreate,
    ProjectSummary,
    ReferenceSuggestion,
    ReferenceSuggestionCreate,
    ReferenceSuggestionStatus,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
    SnowflakeArtifact,
    WorkflowAgentTrace,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)


class WritingDataStore(Protocol):
    def init(self) -> None:
        pass

    def list_projects(self) -> list[ProjectSummary]:
        pass

    def create_project(self, project: ProjectCreate) -> ProjectSummary:
        pass

    def get_project(self, project_id: str) -> ProjectSummary | None:
        pass

    def project_exists(self, project_id: str) -> bool:
        pass

    def advance_project_current_step(
        self, project_id: str, completed_step: int
    ) -> ProjectSummary | None:
        pass

    def list_snowflake_artifacts(self, project_id: str) -> list[SnowflakeArtifact]:
        pass

    def get_snowflake_artifact(
        self, project_id: str, step_number: int
    ) -> SnowflakeArtifact | None:
        pass

    def save_snowflake_artifact(self, artifact: SnowflakeArtifact) -> SnowflakeArtifact:
        pass

    def list_canon_entities(self, project_id: str) -> list[CanonEntity]:
        pass

    def create_canon_entity(
        self, project_id: str, entity: CanonEntityCreate
    ) -> CanonEntity:
        pass

    def update_canon_entity(
        self, project_id: str, entity_id: str, entity: CanonEntityUpdate
    ) -> CanonEntity | None:
        pass

    def delete_canon_entity(self, project_id: str, entity_id: str) -> bool:
        pass

    def list_scene_contracts(self, project_id: str) -> list[SceneContract]:
        pass

    def get_scene_contract(
        self, project_id: str, scene_id: str
    ) -> SceneContract | None:
        pass

    def create_scene_contract(
        self, project_id: str, scene: SceneContractCreate
    ) -> SceneContract:
        pass

    def update_scene_contract(
        self, project_id: str, scene_id: str, scene: SceneContractUpdate
    ) -> SceneContract | None:
        pass

    def delete_scene_contract(self, project_id: str, scene_id: str) -> bool:
        pass

    def list_manuscript_chapters(self, project_id: str) -> list[ManuscriptChapter]:
        pass

    def create_manuscript_chapter(
        self, project_id: str, chapter: ManuscriptChapterCreate
    ) -> ManuscriptChapter:
        pass

    def update_manuscript_chapter(
        self, project_id: str, chapter_id: str, chapter: ManuscriptChapterUpdate
    ) -> ManuscriptChapter | None:
        pass

    def delete_manuscript_chapter(self, project_id: str, chapter_id: str) -> bool:
        pass

    def list_memory_records(self, project_id: str) -> list[MemoryRecord]:
        pass

    def create_memory_record(
        self, project_id: str, record: MemoryRecordCreate
    ) -> MemoryRecord:
        pass

    def update_memory_record(
        self, project_id: str, record_id: str, record: MemoryRecordUpdate
    ) -> MemoryRecord | None:
        pass

    def delete_memory_record(self, project_id: str, record_id: str) -> bool:
        pass

    def list_manuscript_proposals(self, project_id: str) -> list[ManuscriptProposal]:
        pass

    def create_manuscript_proposal(
        self, project_id: str, proposal: ManuscriptProposalCreate
    ) -> ManuscriptProposal:
        pass

    def update_manuscript_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: ManuscriptProposalStatus,
    ) -> ManuscriptProposal | None:
        pass

    def get_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptProposal | None:
        pass

    def list_manuscript_scenes(self, project_id: str) -> list[ManuscriptScene]:
        pass

    def list_manuscript_revisions(self, project_id: str) -> list[ManuscriptRevision]:
        pass

    def get_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptRevision | None:
        pass

    def accept_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptScene | None:
        pass

    def restore_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptScene | None:
        pass

    def update_manuscript_scene(
        self, project_id: str, scene_id: str, update: ManuscriptSceneUpdate
    ) -> ManuscriptScene | None:
        pass

    def list_writeback_proposals(self, project_id: str) -> list[WritebackProposal]:
        pass

    def create_writeback_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal:
        pass

    def create_writeback_proposals(
        self, project_id: str, proposals: list[WritebackProposalCreate]
    ) -> list[WritebackProposal]:
        pass

    def update_writeback_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: WritebackProposalStatus,
    ) -> WritebackProposal | None:
        pass

    def list_reference_suggestions(self, project_id: str) -> list[ReferenceSuggestion]:
        pass

    def create_reference_suggestion(
        self, project_id: str, suggestion: ReferenceSuggestionCreate
    ) -> ReferenceSuggestion:
        pass

    def update_reference_suggestion_status(
        self,
        project_id: str,
        suggestion_id: str,
        suggestion_status: ReferenceSuggestionStatus,
    ) -> ReferenceSuggestion | None:
        pass
