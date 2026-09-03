"""Scene proposal repository: parsed Step 8 proposals (P1-05).

Proposals follow the unified review state machine; accepting a batch of
them creates the real scene contracts inside one transaction, so a
conflict in any sequence rolls the whole batch back. The batch flow
itself coordinates several repositories and lives in app.data.flows.
"""

from __future__ import annotations

import json
import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.models import (
    SceneProposal,
    SceneProposalCreate,
    SceneProposalStatus,
)
from app.review.state_machine import validate_review_transition


class SceneProposalNotFoundError(LookupError):
    def __init__(self, proposal_id: str):
        self.proposal_id = proposal_id
        super().__init__(f"Scene proposal '{proposal_id}' does not exist.")


class SceneProposalReviewedError(ValueError):
    """A decided proposal cannot be accepted again."""


class SceneSequenceConflictError(ValueError):
    """A batch accept would collide with existing scene sequences."""


class SceneChapterMissingError(ValueError):
    """A proposal points at a chapter that does not belong to the project."""


class SceneProposalQualityError(ValueError):
    """A proposal has blocking validation findings and cannot be accepted."""


SCENE_PROPOSAL_COLUMNS = """
    SELECT id, project_id, sequence, chapter_id, chapter_hint, title, pov, goal,
           conflict, turning_point, outcome, required_canon_ids, required_canon_raw,
           forbidden_fact_refs, information_delta, character_state_delta,
           story_thread_actions, open_threads, source_ref, source_excerpt,
           warnings_json, blocking_errors_json, status, applied_scene_id, created_at, reviewed_at
    FROM scene_proposals
"""


def scene_proposal_from_row(row: sqlite3.Row) -> SceneProposal:
    return SceneProposal(
        id=row["id"],
        project_id=row["project_id"],
        sequence=row["sequence"],
        chapter_id=row["chapter_id"],
        chapter_hint=row["chapter_hint"],
        title=row["title"],
        pov=row["pov"],
        goal=row["goal"],
        conflict=row["conflict"],
        turning_point=row["turning_point"],
        outcome=row["outcome"],
        required_canon_ids=row["required_canon_ids"],
        required_canon_raw=row["required_canon_raw"],
        forbidden_fact_refs=row["forbidden_fact_refs"],
        information_delta=row["information_delta"],
        character_state_delta=row["character_state_delta"],
        story_thread_actions=row["story_thread_actions"],
        open_threads=row["open_threads"],
        source_ref=row["source_ref"],
        source_excerpt=row["source_excerpt"],
        warnings=json.loads(row["warnings_json"]),
        blocking_errors=json.loads(row["blocking_errors_json"]),
        status=row["status"],
        applied_scene_id=row["applied_scene_id"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


def scene_proposal_to_params(proposal: SceneProposal) -> tuple:
    return (
        proposal.id,
        proposal.project_id,
        proposal.sequence,
        proposal.chapter_id,
        proposal.chapter_hint,
        proposal.title,
        proposal.pov,
        proposal.goal,
        proposal.conflict,
        proposal.turning_point,
        proposal.outcome,
        proposal.required_canon_ids,
        proposal.required_canon_raw,
        proposal.forbidden_fact_refs,
        proposal.information_delta,
        proposal.character_state_delta,
        proposal.story_thread_actions,
        proposal.open_threads,
        proposal.source_ref,
        proposal.source_excerpt,
        json.dumps(proposal.warnings, ensure_ascii=False),
        json.dumps(proposal.blocking_errors, ensure_ascii=False),
        proposal.status,
        proposal.applied_scene_id,
        proposal.created_at,
        proposal.reviewed_at,
    )


def _insert_params(create: SceneProposalCreate) -> tuple:
    return (
        create.sequence,
        create.chapter_id,
        create.chapter_hint,
        create.title,
        create.pov,
        create.goal,
        create.conflict,
        create.turning_point,
        create.outcome,
        create.required_canon_ids,
        create.required_canon_raw,
        create.forbidden_fact_refs,
        create.information_delta,
        create.character_state_delta,
        create.story_thread_actions,
        create.open_threads,
        create.source_ref,
        create.source_excerpt,
        json.dumps(create.warnings, ensure_ascii=False),
        json.dumps(create.blocking_errors, ensure_ascii=False),
    )


INSERT_SQL = """
    INSERT INTO scene_proposals (
        id, project_id, sequence, chapter_id, chapter_hint, title, pov, goal,
        conflict, turning_point, outcome, required_canon_ids, required_canon_raw,
        forbidden_fact_refs, information_delta, character_state_delta,
        story_thread_actions, open_threads, source_ref, source_excerpt,
        warnings_json, blocking_errors_json, status, applied_scene_id, created_at, reviewed_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', '', ?, '')
"""


def merge_required_canon(proposal: SceneProposal) -> str:
    """Flatten resolved canon ids plus raw names into the contract column."""
    parts = [
        part.strip()
        for part in (proposal.required_canon_ids, proposal.required_canon_raw)
        if part.strip()
    ]
    return "\n".join(parts)


def step_from_source_ref(source_ref: str) -> int:
    # snowflake_artifact:{project_id}:{step_number}
    parts = source_ref.split(":")
    if len(parts) == 3 and parts[0] == "snowflake_artifact":
        try:
            step = int(parts[2])
            if 1 <= step <= 10:
                return step
        except ValueError:
            pass
    return 8


class SceneProposalRepository:
    """SQL for the scene_proposals table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self, project_id: str, status: str | None = None) -> list[SceneProposal]:
        query = f"{SCENE_PROPOSAL_COLUMNS} WHERE project_id = ?"
        params: list[object] = [project_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY sequence, id"
        rows = self.connection.execute(query, params).fetchall()
        return [scene_proposal_from_row(row) for row in rows]

    def get(self, project_id: str, proposal_id: str) -> SceneProposal | None:
        row = self.connection.execute(
            f"{SCENE_PROPOSAL_COLUMNS} WHERE project_id = ? AND id = ?",
            (project_id, proposal_id),
        ).fetchone()
        return scene_proposal_from_row(row) if row else None

    def create_batch(
        self,
        project_id: str,
        proposals: list[SceneProposalCreate],
    ) -> list[SceneProposal]:
        """Persist parsed proposals inside the caller's transaction."""
        if not proposals:
            return []
        now = utc_now()
        existing_ids = {
            row["id"]
            for row in self.connection.execute("SELECT id FROM scene_proposals").fetchall()
        }
        created_list: list[SceneProposal] = []
        params_list = []
        for create in proposals:
            proposal_id = make_record_id(
                f"{project_id}-scene-proposal-s{create.sequence}-{create.title}",
                existing_ids,
            )
            existing_ids.add(proposal_id)
            created = SceneProposal(
                id=proposal_id,
                project_id=project_id,
                status="pending_review",
                applied_scene_id="",
                created_at=now,
                reviewed_at="",
                **create.model_dump(),
            )
            created_list.append(created)
            params_list.append((proposal_id, project_id, *_insert_params(create), now))
        self.connection.executemany(INSERT_SQL, params_list)
        return created_list

    def supersede_pending(
        self,
        *,
        project_id: str,
        source_ref: str,
        except_ids: set[str] | None = None,
    ) -> int:
        """Force re-parse: prior pending proposals for this artifact are stale."""
        excluded = except_ids or set()
        rows = self.connection.execute(
            f"""
            {SCENE_PROPOSAL_COLUMNS}
            WHERE project_id = ? AND source_ref = ? AND status = 'pending_review'
            """,
            (project_id, source_ref),
        ).fetchall()
        stale = [row["id"] for row in rows if row["id"] not in excluded]
        if not stale:
            return 0
        now = utc_now()
        placeholders = ", ".join("?" for _ in stale)
        cursor = self.connection.execute(
            f"""
            UPDATE scene_proposals
            SET status = 'superseded',
                reviewed_at = ?
            WHERE id IN ({placeholders})
            """,
            (now, *stale),
        )
        return cursor.rowcount

    def update_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: SceneProposalStatus,
    ) -> SceneProposal | None:
        reviewed_at = utc_now()
        current = self.get(project_id, proposal_id)
        if current is None:
            return None
        if current.status == proposal_status:
            return current
        validate_review_transition(current.status, proposal_status, "Scene proposal")
        cursor = self.connection.execute(
            """
            UPDATE scene_proposals
            SET status = ?,
                reviewed_at = ?
            WHERE project_id = ? AND id = ? AND status = ?
            """,
            (proposal_status, reviewed_at, project_id, proposal_id, current.status),
        )
        if cursor.rowcount == 0:
            raise ValueError("Scene proposal changed concurrently; retry.")
        return self.get(project_id, proposal_id)

    def mark_accepted(
        self,
        *,
        project_id: str,
        proposal_id: str,
        applied_scene_id: str,
        reviewed_at: str,
    ) -> int:
        """Accept exactly one pending proposal; returns the affected rows."""
        cursor = self.connection.execute(
            """
            UPDATE scene_proposals
            SET status = 'accepted',
                reviewed_at = ?,
                applied_scene_id = ?
            WHERE project_id = ? AND id = ? AND status = 'pending_review'
            """,
            (reviewed_at, applied_scene_id, project_id, proposal_id),
        )
        return cursor.rowcount
