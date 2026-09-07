from __future__ import annotations

import sqlite3
from typing import Protocol

from app.data.ports.generation import GenerationRecorder
from app.data.ports.reading import ProjectSnapshotReader, ReviewTargetReader
from app.models import (
    ManuscriptRevision,
    SceneContract,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)


class WritebackDataPort(ProjectSnapshotReader, ReviewTargetReader, GenerationRecorder, Protocol):
    def create_writeback_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal: ...

    def get_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptRevision | None: ...

    def get_scene_contract(
        self, project_id: str, scene_id: str, connection: sqlite3.Connection | None = None
    ) -> SceneContract | None: ...

    def list_writeback_proposals(self, project_id: str) -> list[WritebackProposal]: ...

    def update_writeback_proposal_status(
        self, project_id: str, proposal_id: str, proposal_status: WritebackProposalStatus
    ) -> WritebackProposal | None: ...
