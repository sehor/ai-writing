from __future__ import annotations

import sqlite3
from typing import Protocol

from app.data.ports.analysis import AnalysisDataPort
from app.models import (
    SceneContract,
    SceneProposal,
    SceneProposalCreate,
    SceneProposalStatus,
    SnowflakeRecordRevision,
    WritebackProposal,
)


class CompileDataPort(AnalysisDataPort, Protocol):
    def accept_scene_proposals(
        self, project_id: str, proposal_ids: list[str]
    ) -> tuple[list[SceneContract], list[SceneProposal]]: ...

    def create_scene_proposals(
        self,
        project_id: str,
        proposals: list[SceneProposalCreate],
        connection: sqlite3.Connection | None = None,
    ) -> list[SceneProposal]: ...

    def get_scene_proposal(
        self, project_id: str, proposal_id: str, connection: sqlite3.Connection | None = None
    ) -> SceneProposal | None: ...

    def list_accepted_snowflake_records(
        self, project_id: str, step_number: int
    ) -> list[SnowflakeRecordRevision]: ...

    def list_scene_contracts(self, project_id: str) -> list[SceneContract]: ...

    def list_scene_proposals(
        self, project_id: str, status: str | None = None
    ) -> list[SceneProposal]: ...

    def list_writeback_proposals(self, project_id: str) -> list[WritebackProposal]: ...

    def supersede_pending_scene_proposals(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
        except_ids: set[str] | None = None,
    ) -> int: ...

    def update_scene_proposal_status(
        self, project_id: str, proposal_id: str, proposal_status: SceneProposalStatus
    ) -> SceneProposal | None: ...
