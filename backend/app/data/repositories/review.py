"""Review repository: unified-review-state records.

Covers write-back proposals and reference suggestions - the two tables
whose rows move through the shared pending_review / accepted / rejected /
superseded state machine. Accepting an update write-back also touches
canon/memory rows; that cross-aggregate flow lives in app.data.flows.
"""

import json
import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.models import (
    ReferenceSuggestion,
    ReferenceSuggestionCreate,
    ReferenceSuggestionStatus,
    WorkflowAgentTrace,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)
from app.review.state_machine import validate_review_transition


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
        target_record_id=row["target_record_id"],
        expected_version=row["expected_version"] or None,
        changes=json.loads(row["changes_json"]),
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        applied_record_id=row["applied_record_id"],
    )


WRITEBACK_PROPOSAL_COLUMNS = """
    SELECT id, project_id, target, action, title, rationale, payload_json,
           source_ref, target_record_id, expected_version, changes_json,
           status, created_at, reviewed_at, applied_record_id
    FROM writeback_proposals
"""


def writeback_proposal_to_params(
    proposal: WritebackProposal,
) -> tuple:
    return (
        proposal.id,
        proposal.project_id,
        proposal.target,
        proposal.action,
        proposal.title,
        proposal.rationale,
        json.dumps(proposal.payload),
        proposal.source_ref,
        proposal.target_record_id,
        proposal.expected_version,
        json.dumps(proposal.changes),
        proposal.status,
        proposal.created_at,
        proposal.reviewed_at,
        proposal.applied_record_id,
    )


def reference_suggestion_from_row(row: sqlite3.Row) -> ReferenceSuggestion:
    return ReferenceSuggestion(
        editor_context=json.loads(dict(row).get("editor_context_json") or "null"),
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
) -> tuple:
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
        suggestion.editor_context.model_dump_json() if suggestion.editor_context else None,
    )


class ReviewRepository:
    """SQL for writeback_proposals and reference_suggestions."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    # ------------------------------------------------------------------
    # Write-back proposals
    # ------------------------------------------------------------------

    def list_writebacks(self, project_id: str) -> list[WritebackProposal]:
        rows = self.connection.execute(
            f"""
            {WRITEBACK_PROPOSAL_COLUMNS}
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        return [writeback_proposal_from_row(row) for row in rows]

    def get_writeback(self, project_id: str, proposal_id: str) -> WritebackProposal | None:
        row = self.connection.execute(
            f"""
            {WRITEBACK_PROPOSAL_COLUMNS}
            WHERE project_id = ? AND id = ?
            """,
            (project_id, proposal_id),
        ).fetchone()
        return writeback_proposal_from_row(row) if row else None

    def create_writeback_batch(
        self,
        project_id: str,
        proposals: list[WritebackProposalCreate],
    ) -> list[WritebackProposal]:
        if not proposals:
            return []
        now = utc_now()
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM writeback_proposals",
            ).fetchall()
        }
        created_list = []
        params_list = []
        for proposal in proposals:
            created = WritebackProposal(
                id=make_record_id(
                    f"{project_id}-writeback-{proposal.target}-{proposal.title}",
                    existing_ids,
                ),
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

        self.connection.executemany(
            """
            INSERT INTO writeback_proposals (
                id, project_id, target, action, title, rationale, payload_json,
                source_ref, target_record_id, expected_version, changes_json,
                status, created_at, reviewed_at, applied_record_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params_list,
        )
        return created_list

    def supersede_pending_for_target(
        self,
        *,
        project_id: str,
        keep_proposal_id: str,
        target_record_id: str,
        reviewed_at: str,
    ) -> int:
        """Mark sibling pending update proposals for one record as superseded."""
        cursor = self.connection.execute(
            """
            UPDATE writeback_proposals
            SET status = 'superseded',
                reviewed_at = ?
            WHERE project_id = ?
              AND id <> ?
              AND status = 'pending_review'
              AND target = 'canon_entity'
              AND action = 'update'
              AND target_record_id = ?
            """,
            (reviewed_at, project_id, keep_proposal_id, target_record_id),
        )
        return cursor.rowcount

    def supersede_pending_for_source(self, *, project_id: str, source_ref: str) -> int:
        """Force re-run (P1-05): all pending proposals of one source go stale."""
        cursor = self.connection.execute(
            """
            UPDATE writeback_proposals
            SET status = 'superseded',
                reviewed_at = ?
            WHERE project_id = ?
              AND source_ref = ?
              AND status = 'pending_review'
            """,
            (utc_now(), project_id, source_ref),
        )
        return cursor.rowcount

    def mark_writeback_accepted(
        self,
        *,
        project_id: str,
        proposal_id: str,
        applied_record_id: str,
        reviewed_at: str,
    ) -> int:
        cursor = self.connection.execute(
            """
            UPDATE writeback_proposals
            SET status = ?,
                reviewed_at = ?,
                applied_record_id = ?
            WHERE project_id = ? AND id = ? AND status = 'pending_review'
            """,
            ("accepted", reviewed_at, applied_record_id, project_id, proposal_id),
        )
        return cursor.rowcount

    def update_writeback_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: WritebackProposalStatus,
    ) -> WritebackProposal | None:
        """Non-accepting transition; accepting goes through app.data.flows."""
        reviewed_at = utc_now()
        current = self.get_writeback(project_id, proposal_id)
        if current is None:
            return None
        if current.status == proposal_status:
            return current
        validate_review_transition(current.status, proposal_status, "Write-back proposal")
        cursor = self.connection.execute(
            """
            UPDATE writeback_proposals
            SET status = ?,
                reviewed_at = ?
            WHERE project_id = ? AND id = ? AND status = ?
            """,
            (proposal_status, reviewed_at, project_id, proposal_id, current.status),
        )
        if cursor.rowcount == 0:
            raise ValueError("Write-back proposal changed concurrently; retry.")
        return self.get_writeback(project_id, proposal_id)

    # ------------------------------------------------------------------
    # Reference suggestions
    # ------------------------------------------------------------------

    REFERENCE_SUGGESTION_COLUMNS = """
        SELECT id, project_id, suggestion_type, scope_type, scope_ref,
               title, content, rationale, used_context,
               canon_warnings_json, style_notes_json, graph_warnings_json,
               proposed_writebacks_json, workflow_trace_json,
               status, created_at, reviewed_at, editor_context_json
        FROM reference_suggestions
    """

    def list_references(self, project_id: str) -> list[ReferenceSuggestion]:
        rows = self.connection.execute(
            f"""
            {self.REFERENCE_SUGGESTION_COLUMNS}
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        return [reference_suggestion_from_row(row) for row in rows]

    def get_reference(self, project_id: str, suggestion_id: str) -> ReferenceSuggestion | None:
        row = self.connection.execute(
            f"""
            {self.REFERENCE_SUGGESTION_COLUMNS}
            WHERE project_id = ? AND id = ?
            """,
            (project_id, suggestion_id),
        ).fetchone()
        return reference_suggestion_from_row(row) if row else None

    def create_reference(
        self, project_id: str, suggestion: ReferenceSuggestionCreate
    ) -> ReferenceSuggestion:
        now = utc_now()
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM reference_suggestions",
            ).fetchall()
        }
        created = ReferenceSuggestion(
            id=make_record_id(
                f"{project_id}-reference-{suggestion.suggestion_type}-{suggestion.title}",
                existing_ids,
            ),
            project_id=project_id,
            status="pending_review",
            created_at=now,
            reviewed_at="",
            **suggestion.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO reference_suggestions (
                id, project_id, suggestion_type, scope_type, scope_ref,
                title, content, rationale, used_context,
                canon_warnings_json, style_notes_json, graph_warnings_json,
                proposed_writebacks_json, workflow_trace_json,
                status, created_at, reviewed_at, editor_context_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            reference_suggestion_to_params(created),
        )
        return created

    def update_reference_status(
        self,
        project_id: str,
        suggestion_id: str,
        suggestion_status: ReferenceSuggestionStatus,
    ) -> ReferenceSuggestion | None:
        reviewed_at = utc_now()
        current = self.get_reference(project_id, suggestion_id)
        if current is None:
            return None
        if current.status == suggestion_status:
            return current
        validate_review_transition(current.status, suggestion_status, "Reference suggestion")
        cursor = self.connection.execute(
            """
            UPDATE reference_suggestions
            SET status = ?,
                reviewed_at = ?
            WHERE project_id = ? AND id = ? AND status = ?
            """,
            (suggestion_status, reviewed_at, project_id, suggestion_id, current.status),
        )
        if cursor.rowcount == 0:
            return None
        return self.get_reference(project_id, suggestion_id)
