from __future__ import annotations

from typing import Protocol

from app.data.ports.reading import NarrativeSnapshotReader
from app.data.ports.generation import GenerationRecorder
from app.models import (
    ManuscriptChapter,
    ManuscriptProposal,
    ManuscriptProposalAcceptance,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    SnowflakeArtifactRevision,
)


class ManuscriptDataPort(NarrativeSnapshotReader, GenerationRecorder, Protocol):
    def accept_manuscript_proposal(
        self, project_id: str, proposal_id: str, draft: ManuscriptProposalAcceptance | None = None
    ) -> ManuscriptScene | None: ...

    def create_manuscript_proposal(
        self, project_id: str, proposal: ManuscriptProposalCreate
    ) -> ManuscriptProposal: ...

    def get_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptProposal | None: ...

    def get_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptRevision | None: ...

    def get_manuscript_scene(self, project_id: str, scene_id: str) -> ManuscriptScene | None: ...

    def get_snowflake_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeArtifactRevision | None: ...

    def list_manuscript_chapters(self, project_id: str) -> list[ManuscriptChapter]: ...

    def restore_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptScene | None: ...

    def update_manuscript_proposal_status(
        self, project_id: str, proposal_id: str, proposal_status: ManuscriptProposalStatus
    ) -> ManuscriptProposal | None: ...

    def update_manuscript_scene(
        self, project_id: str, scene_id: str, update: ManuscriptSceneUpdate
    ) -> ManuscriptScene | None: ...
