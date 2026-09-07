from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from typing import Protocol

from app.analysis.models import AnalysisRun
from app.data.ports.reading import ReviewTargetReader
from app.models import WritebackProposal, WritebackProposalCreate


class AnalysisDataPort(ReviewTargetReader, Protocol):
    def connect(self) -> AbstractContextManager[sqlite3.Connection]: ...

    def create_writeback_proposals(
        self,
        project_id: str,
        proposals: list[WritebackProposalCreate],
        connection: sqlite3.Connection | None = None,
    ) -> list[WritebackProposal]: ...

    def get_analysis_run(
        self, project_id: str, source_ref: str, processor: str, input_hash: str | None = None
    ) -> AnalysisRun | None: ...

    def get_writeback_proposal(
        self, project_id: str, proposal_id: str, connection: sqlite3.Connection | None = None
    ) -> WritebackProposal | None: ...

    def record_analysis_run(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
        processor: str,
        input_hash: str,
        status: str,
        result_json: dict,
    ) -> AnalysisRun: ...

    def supersede_pending_writebacks_for_source(
        self, connection: sqlite3.Connection, *, project_id: str, source_ref: str
    ) -> int: ...
