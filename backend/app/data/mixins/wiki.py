import json
import sqlite3

from app.models import (
    CanonEntityCreate,
    MemoryRecordCreate,
    ReferenceSuggestion,
    ReferenceSuggestionCreate,
    ReferenceSuggestionStatus,
    WorkflowAgentTrace,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)
from app.data.helpers import make_record_id, utc_now
from app.review.state_machine import validate_review_transition
from app.review.writeback_apply import (
    WritebackTargetMissingError,
    WritebackVersionConflictError,
    apply_canon_update,
    validate_update_proposal,
)


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
                f"""
                {WRITEBACK_PROPOSAL_COLUMNS}
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [writeback_proposal_from_row(row) for row in rows]

    def get_writeback_proposal(
        self,
        project_id: str,
        proposal_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> WritebackProposal | None:
        if connection is None:
            with self.connect() as owned:
                return self.get_writeback_proposal(project_id, proposal_id, owned)
        row = connection.execute(
            f"""
            {WRITEBACK_PROPOSAL_COLUMNS}
            WHERE project_id = ? AND id = ?
            """,
            (project_id, proposal_id),
        ).fetchone()
        return writeback_proposal_from_row(row) if row else None

    def create_writeback_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal:
        created_list = self.create_writeback_proposals(project_id, [proposal])
        return created_list[0]

    def create_writeback_proposals(
        self,
        project_id: str,
        proposals: list[WritebackProposalCreate],
        connection: sqlite3.Connection | None = None,
    ) -> list[WritebackProposal]:
        if not proposals:
            return []
        if connection is None:
            with self.connect() as owned:
                return self.create_writeback_proposals(project_id, proposals, owned)
        now = utc_now()
        existing_ids = {
            row["id"]
            for row in connection.execute(
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

        connection.executemany(
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

    def supersede_pending_writebacks_for_target(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        keep_proposal_id: str,
        target_record_id: str,
        reviewed_at: str,
    ) -> int:
        """Mark sibling pending update proposals for one record as superseded."""
        cursor = connection.execute(
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

    def supersede_pending_writebacks_for_source(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
    ) -> int:
        """Force re-run (P1-05): all pending proposals of one source go stale."""
        cursor = connection.execute(
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

    def update_writeback_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: WritebackProposalStatus,
    ) -> WritebackProposal | None:
        if proposal_status == "accepted":
            return self.accept_writeback_proposal(project_id, proposal_id)

        reviewed_at = utc_now()
        with self.connect() as connection:
            current = self.get_writeback_proposal(project_id, proposal_id, connection)
            if current is None:
                return None
            if current.status == proposal_status:
                return current
            validate_review_transition(current.status, proposal_status, "Write-back proposal")
            cursor = connection.execute(
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
            return self.get_writeback_proposal(project_id, proposal_id, connection)

    def accept_writeback_proposal(
        self, project_id: str, proposal_id: str
    ) -> WritebackProposal | None:
        with self.connect() as connection:
            proposal = self.get_writeback_proposal(project_id, proposal_id, connection)
            if proposal is None:
                return None
            if proposal.status == "accepted":
                return proposal
            if proposal.status != "pending_review":
                raise ValueError("Write-back proposal is already reviewed.")

            if proposal.action == "update":
                applied = self._apply_canon_update_proposal(connection, project_id, proposal)
            elif proposal.target == "canon_entity":
                applied = self.create_canon_entity(
                    project_id,
                    CanonEntityCreate.model_validate(proposal.payload),
                    connection,
                )
            else:
                applied = self.create_memory_record(
                    project_id,
                    MemoryRecordCreate.model_validate(proposal.payload),
                    connection,
                )

            reviewed_at = utc_now()
            cursor = connection.execute(
                """
                UPDATE writeback_proposals
                SET status = ?,
                    reviewed_at = ?,
                    applied_record_id = ?
                WHERE project_id = ? AND id = ? AND status = 'pending_review'
                """,
                ("accepted", reviewed_at, applied.id, project_id, proposal_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("Write-back proposal is already reviewed.")
            if proposal.action == "update":
                # Sibling update proposals for the same record are now stale;
                # they must not be silently accepted afterwards.
                self.supersede_pending_writebacks_for_target(
                    connection,
                    project_id=project_id,
                    keep_proposal_id=proposal.id,
                    target_record_id=proposal.target_record_id,
                    reviewed_at=reviewed_at,
                )
            return self.get_writeback_proposal(project_id, proposal_id, connection)

    def _apply_canon_update_proposal(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        proposal: WritebackProposal,
    ):
        validate_update_proposal(proposal)
        current = self.get_canon_entity(project_id, proposal.target_record_id, connection)
        if current is None:
            raise WritebackTargetMissingError(proposal.target_record_id)
        if current.version != proposal.expected_version:
            raise WritebackVersionConflictError(
                proposal.target_record_id,
                proposal.expected_version,
                current.version,
            )
        updated = apply_canon_update(
            current,
            proposal,
            new_version=current.version + 1,
            updated_at=utc_now(),
        )
        cursor = connection.execute(
            """
            UPDATE canon_entities
            SET entity_type = ?,
                name = ?,
                summary = ?,
                current_state = ?,
                constraints = ?,
                last_seen = ?,
                timeline_notes = ?,
                version = ?,
                updated_at = ?
            WHERE project_id = ? AND id = ? AND version = ?
            """,
            (
                updated.entity_type,
                updated.name,
                updated.summary,
                updated.current_state,
                updated.constraints,
                updated.last_seen,
                updated.timeline_notes,
                updated.version,
                updated.updated_at,
                project_id,
                current.id,
                current.version,
            ),
        )
        if cursor.rowcount == 0:
            raise WritebackVersionConflictError(
                proposal.target_record_id,
                proposal.expected_version,
                current.version,
            )
        return updated

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
        reviewed_at = utc_now()
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
            if row is None:
                return None
            current = reference_suggestion_from_row(row)
            if current.status == suggestion_status:
                return current
            validate_review_transition(current.status, suggestion_status, "Reference suggestion")
            cursor = connection.execute(
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
