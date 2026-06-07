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
from app.data.helpers import ensure_column, make_record_id, utc_now

def writeback_proposal_from_row(row: sqlite3.Row) -> WritebackProposal:
    return WritebackProposal(
        id=row["id"],
        project_id=row["project_id"],
        target=row["target"],
        action=row["action"],
        title=row["title"],
        rationale=row["rationale"],
        payload=json.loads(row["payload_json"]),
        source_ref=row["source_ref"],
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        applied_record_id=row["applied_record_id"],
    )
def writeback_proposal_to_params(
    proposal: WritebackProposal,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str]:
    return (
        proposal.id,
        proposal.project_id,
        proposal.target,
        proposal.action,
        proposal.title,
        proposal.rationale,
        json.dumps(proposal.payload),
        proposal.source_ref,
        proposal.status,
        proposal.created_at,
        proposal.reviewed_at,
        proposal.applied_record_id,
    )
def reference_suggestion_from_row(row: sqlite3.Row) -> ReferenceSuggestion:
    return ReferenceSuggestion(
        id=row["id"],
        project_id=row["project_id"],
        suggestion_type=row["suggestion_type"],
        scope_type=row["scope_type"],
        scope_ref=row["scope_ref"],
        title=row["title"],
        content=row["content"],
        rationale=row["rationale"],
        used_context=row["used_context"],
        canon_warnings=json.loads(row["canon_warnings_json"]),
        style_notes=json.loads(row["style_notes_json"]),
        graph_warnings=json.loads(row["graph_warnings_json"]),
        proposed_writebacks=[
            WritebackProposalCreate.model_validate(item)
            for item in json.loads(row["proposed_writebacks_json"])
        ],
        workflow_trace=[
            WorkflowAgentTrace.model_validate(item)
            for item in json.loads(row["workflow_trace_json"])
        ],
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )
def reference_suggestion_to_params(
    suggestion: ReferenceSuggestion,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    return (
        suggestion.id,
        suggestion.project_id,
        suggestion.suggestion_type,
        suggestion.scope_type,
        suggestion.scope_ref,
        suggestion.title,
        suggestion.content,
        suggestion.rationale,
        suggestion.used_context,
        json.dumps(suggestion.canon_warnings),
        json.dumps(suggestion.style_notes),
        json.dumps(suggestion.graph_warnings),
        json.dumps([proposal.model_dump() for proposal in suggestion.proposed_writebacks]),
        json.dumps([trace.model_dump() for trace in suggestion.workflow_trace]),
        suggestion.status,
        suggestion.created_at,
        suggestion.reviewed_at,
    )

class WikiDataMixin:
    def list_writeback_proposals(self, project_id: str) -> list[WritebackProposal]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, target, action, title, rationale, payload_json,
                       source_ref, status, created_at, reviewed_at, applied_record_id
                FROM writeback_proposals
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [writeback_proposal_from_row(row) for row in rows]
    def create_writeback_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal:
        now = utc_now()
        with self.connect() as connection:
            existing_ids = {
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM writeback_proposals WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            created = WritebackProposal(
                id=make_record_id(f"writeback-{proposal.target}-{proposal.title}", existing_ids),
                project_id=project_id,
                status="pending_review",
                created_at=now,
                reviewed_at="",
                applied_record_id="",
                **proposal.model_dump(),
            )
            connection.execute(
                """
                INSERT INTO writeback_proposals (
                    id, project_id, target, action, title, rationale, payload_json,
                    source_ref, status, created_at, reviewed_at, applied_record_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                writeback_proposal_to_params(created),
            )
        return created
    def create_writeback_proposals(
        self, project_id: str, proposals: list[WritebackProposalCreate]
    ) -> list[WritebackProposal]:
        if not proposals:
            return []
        now = utc_now()
        with self.connect() as connection:
            existing_ids = {
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM writeback_proposals WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            created_list = []
            params_list = []
            for proposal in proposals:
                created = WritebackProposal(
                    id=make_record_id(f"writeback-{proposal.target}-{proposal.title}", existing_ids),
                    project_id=project_id,
                    status="pending_review",
                    created_at=now,
                    reviewed_at="",
                    applied_record_id="",
                    **proposal.model_dump(),
                )
                existing_ids.add(created.id)
                created_list.append(created)
                params_list.append(writeback_proposal_to_params(created))

            connection.executemany(
                """
                INSERT INTO writeback_proposals (
                    id, project_id, target, action, title, rationale, payload_json,
                    source_ref, status, created_at, reviewed_at, applied_record_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                params_list,
            )
        return created_list
    def update_writeback_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: WritebackProposalStatus,
    ) -> WritebackProposal | None:
        if proposal_status == "accepted":
            return self.accept_writeback_proposal(project_id, proposal_id)

        reviewed_at = utc_now() if proposal_status != "pending_review" else ""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE writeback_proposals
                SET status = ?,
                    reviewed_at = ?
                WHERE project_id = ? AND id = ?
                """,
                (proposal_status, reviewed_at, project_id, proposal_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT id, project_id, target, action, title, rationale, payload_json,
                       source_ref, status, created_at, reviewed_at, applied_record_id
                FROM writeback_proposals
                WHERE project_id = ? AND id = ?
                """,
                (project_id, proposal_id),
            ).fetchone()
        return writeback_proposal_from_row(row) if row else None
    def accept_writeback_proposal(
        self, project_id: str, proposal_id: str
    ) -> WritebackProposal | None:
        proposal = self.get_writeback_proposal(project_id, proposal_id)
        if proposal is None:
            return None
        if proposal.status == "accepted":
            return proposal

        if proposal.target == "canon_entity":
            applied = self.create_canon_entity(
                project_id,
                CanonEntityCreate.model_validate(proposal.payload),
            )
            applied_record_id = applied.id
        else:
            applied = self.create_memory_record(
                project_id,
                MemoryRecordCreate.model_validate(proposal.payload),
            )
            applied_record_id = applied.id

        reviewed_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE writeback_proposals
                SET status = ?,
                    reviewed_at = ?,
                    applied_record_id = ?
                WHERE project_id = ? AND id = ?
                """,
                ("accepted", reviewed_at, applied_record_id, project_id, proposal_id),
            )
        return self.get_writeback_proposal(project_id, proposal_id)
    def get_writeback_proposal(
        self, project_id: str, proposal_id: str
    ) -> WritebackProposal | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, target, action, title, rationale, payload_json,
                       source_ref, status, created_at, reviewed_at, applied_record_id
                FROM writeback_proposals
                WHERE project_id = ? AND id = ?
                """,
                (project_id, proposal_id),
            ).fetchone()
        return writeback_proposal_from_row(row) if row else None
    def list_reference_suggestions(self, project_id: str) -> list[ReferenceSuggestion]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, suggestion_type, scope_type, scope_ref,
                       title, content, rationale, used_context,
                       canon_warnings_json, style_notes_json, graph_warnings_json,
                       proposed_writebacks_json, workflow_trace_json,
                       status, created_at, reviewed_at
                FROM reference_suggestions
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [reference_suggestion_from_row(row) for row in rows]
    def create_reference_suggestion(
        self, project_id: str, suggestion: ReferenceSuggestionCreate
    ) -> ReferenceSuggestion:
        now = utc_now()
        with self.connect() as connection:
            existing_ids = {
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM reference_suggestions WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            created = ReferenceSuggestion(
                id=make_record_id(f"reference-{suggestion.suggestion_type}-{suggestion.title}", existing_ids),
                project_id=project_id,
                status="pending_review",
                created_at=now,
                reviewed_at="",
                **suggestion.model_dump(),
            )
            connection.execute(
                """
                INSERT INTO reference_suggestions (
                    id, project_id, suggestion_type, scope_type, scope_ref,
                    title, content, rationale, used_context,
                    canon_warnings_json, style_notes_json, graph_warnings_json,
                    proposed_writebacks_json, workflow_trace_json,
                    status, created_at, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                reference_suggestion_to_params(created),
            )
        return created
    def update_reference_suggestion_status(
        self,
        project_id: str,
        suggestion_id: str,
        suggestion_status: ReferenceSuggestionStatus,
    ) -> ReferenceSuggestion | None:
        reviewed_at = utc_now() if suggestion_status != "pending_review" else ""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE reference_suggestions
                SET status = ?,
                    reviewed_at = ?
                WHERE project_id = ? AND id = ?
                """,
                (suggestion_status, reviewed_at, project_id, suggestion_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT id, project_id, suggestion_type, scope_type, scope_ref,
                       title, content, rationale, used_context,
                       canon_warnings_json, style_notes_json, graph_warnings_json,
                       proposed_writebacks_json, workflow_trace_json,
                       status, created_at, reviewed_at
                FROM reference_suggestions
                WHERE project_id = ? AND id = ?
                """,
                (project_id, suggestion_id),
            ).fetchone()
        return reference_suggestion_from_row(row) if row else None
    def get_reference_suggestion(
        self, project_id: str, suggestion_id: str
    ) -> ReferenceSuggestion | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, suggestion_type, scope_type, scope_ref,
                       title, content, rationale, used_context,
                       canon_warnings_json, style_notes_json, graph_warnings_json,
                       proposed_writebacks_json, workflow_trace_json,
                       status, created_at, reviewed_at
                FROM reference_suggestions
                WHERE project_id = ? AND id = ?
                """,
                (project_id, suggestion_id),
            ).fetchone()
        return reference_suggestion_from_row(row) if row else None
