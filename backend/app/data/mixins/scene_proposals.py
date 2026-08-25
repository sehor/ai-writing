"""Persistence for parsed Step 8 Scene Contract proposals (P1-05).

Proposals follow the unified review state machine; accepting a batch of
them creates the real scene contracts inside one transaction, so a
conflict in any sequence rolls the whole batch back.
"""

import json
import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.models import (
    SceneContract,
    SceneContractCreate,
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


SCENE_PROPOSAL_COLUMNS = """
    SELECT id, project_id, sequence, chapter_id, chapter_hint, title, pov, goal,
           conflict, turning_point, required_canon_ids, required_canon_raw,
           forbidden_fact_refs, open_threads, source_ref, source_excerpt,
           warnings_json, status, applied_scene_id, created_at, reviewed_at
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
        required_canon_ids=row["required_canon_ids"],
        required_canon_raw=row["required_canon_raw"],
        forbidden_fact_refs=row["forbidden_fact_refs"],
        open_threads=row["open_threads"],
        source_ref=row["source_ref"],
        source_excerpt=row["source_excerpt"],
        warnings=json.loads(row["warnings_json"]),
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
        proposal.required_canon_ids,
        proposal.required_canon_raw,
        proposal.forbidden_fact_refs,
        proposal.open_threads,
        proposal.source_ref,
        proposal.source_excerpt,
        json.dumps(proposal.warnings, ensure_ascii=False),
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
        create.required_canon_ids,
        create.required_canon_raw,
        create.forbidden_fact_refs,
        create.open_threads,
        create.source_ref,
        create.source_excerpt,
        json.dumps(create.warnings, ensure_ascii=False),
    )


INSERT_SQL = """
    INSERT INTO scene_proposals (
        id, project_id, sequence, chapter_id, chapter_hint, title, pov, goal,
        conflict, turning_point, required_canon_ids, required_canon_raw,
        forbidden_fact_refs, open_threads, source_ref, source_excerpt,
        warnings_json, status, applied_scene_id, created_at, reviewed_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', '', ?, '')
"""


class SceneProposalsDataMixin:
    def list_scene_proposals(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[SceneProposal]:
        query = f"{SCENE_PROPOSAL_COLUMNS} WHERE project_id = ?"
        params: list[object] = [project_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY sequence, id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [scene_proposal_from_row(row) for row in rows]

    def get_scene_proposal(
        self,
        project_id: str,
        proposal_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> SceneProposal | None:
        if connection is None:
            with self.connect() as owned:
                return self.get_scene_proposal(project_id, proposal_id, owned)
        row = connection.execute(
            f"{SCENE_PROPOSAL_COLUMNS} WHERE project_id = ? AND id = ?",
            (project_id, proposal_id),
        ).fetchone()
        return scene_proposal_from_row(row) if row else None

    def create_scene_proposals(
        self,
        project_id: str,
        proposals: list[SceneProposalCreate],
        connection: sqlite3.Connection | None = None,
    ) -> list[SceneProposal]:
        """Persist parsed proposals inside the caller's transaction."""
        if not proposals:
            return []
        if connection is None:
            with self.connect() as owned:
                return self.create_scene_proposals(project_id, proposals, owned)
        now = utc_now()
        existing_ids = {
            row["id"] for row in connection.execute("SELECT id FROM scene_proposals").fetchall()
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
        connection.executemany(INSERT_SQL, params_list)
        return created_list

    def supersede_pending_scene_proposals(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
        except_ids: set[str] | None = None,
    ) -> int:
        """Force re-parse: prior pending proposals for this artifact are stale."""
        excluded = except_ids or set()
        rows = connection.execute(
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
        cursor = connection.execute(
            f"""
            UPDATE scene_proposals
            SET status = 'superseded',
                reviewed_at = ?
            WHERE id IN ({placeholders})
            """,
            (now, *stale),
        )
        return cursor.rowcount

    def update_scene_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: SceneProposalStatus,
    ) -> SceneProposal | None:
        reviewed_at = utc_now()
        with self.connect() as connection:
            current = self.get_scene_proposal(project_id, proposal_id, connection)
            if current is None:
                return None
            if current.status == proposal_status:
                return current
            validate_review_transition(current.status, proposal_status, "Scene proposal")
            cursor = connection.execute(
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
            return self.get_scene_proposal(project_id, proposal_id, connection)

    def accept_scene_proposals(
        self,
        project_id: str,
        proposal_ids: list[str],
    ) -> tuple[list[SceneContract], list[SceneProposal]]:
        """Batch-accept pending proposals into scene contracts.

        One transaction creates every contract and marks every proposal
        accepted; any validation failure raises before a single insert,
        and an insert failure rolls the whole batch back.
        """
        with self.connect() as connection:
            proposals = [
                self.get_scene_proposal(project_id, proposal_id, connection)
                for proposal_id in proposal_ids
            ]
            missing = [
                proposal_id
                for proposal_id, proposal in zip(proposal_ids, proposals)
                if proposal is None
            ]
            if missing:
                raise SceneProposalNotFoundError(missing[0])

            blocked = [
                proposal
                for proposal in proposals
                if proposal.status not in ("pending_review", "accepted")
            ]
            if blocked:
                # Rejected / superseded proposals are terminal; accepting
                # them would violate the unified review state machine.
                first = blocked[0]
                raise SceneProposalReviewedError(
                    f"Scene proposal '{first.id}' is already reviewed "
                    f"(status '{first.status}'); accepting it again is not allowed."
                )

            ordered = sorted(
                (proposal for proposal in proposals if proposal.status == "pending_review"),
                key=lambda proposal: (proposal.sequence, proposal.id),
            )
            already_accepted = [proposal for proposal in proposals if proposal.status == "accepted"]

            # Pre-validation before any insert so nothing partial is written.
            chapter_ids = {chapter.id for chapter in self.list_manuscript_chapters(project_id)}
            seen_sequences: dict[int, str] = {}
            for proposal in ordered:
                if proposal.sequence in seen_sequences:
                    raise SceneSequenceConflictError(
                        f"Proposals '{seen_sequences[proposal.sequence]}' and "
                        f"'{proposal.id}' both use scene sequence {proposal.sequence}."
                    )
                seen_sequences[proposal.sequence] = proposal.id
                if proposal.chapter_id and proposal.chapter_id not in chapter_ids:
                    raise SceneChapterMissingError(
                        f"Scene proposal '{proposal.id}' references chapter "
                        f"'{proposal.chapter_id}', which does not belong to this project."
                    )

            existing_sequences = {
                row["sequence"]
                for row in connection.execute(
                    "SELECT sequence FROM scene_contracts WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            clashes = sorted(set(seen_sequences) & existing_sequences)
            if clashes:
                raise SceneSequenceConflictError(
                    "Scene sequence already exists for this project: "
                    + ", ".join(str(number) for number in clashes)
                    + "."
                )

            now = utc_now()
            created_scenes = []
            for proposal in ordered:
                scene = self.insert_scene_contract(
                    project_id,
                    SceneContractCreate(
                        chapter_id=proposal.chapter_id,
                        sequence=proposal.sequence,
                        title=proposal.title,
                        pov=proposal.pov,
                        goal=proposal.goal,
                        conflict=proposal.conflict,
                        turning_point=proposal.turning_point,
                        required_canon=_merge_required_canon(proposal),
                        forbidden_facts=proposal.forbidden_fact_refs,
                        open_threads=proposal.open_threads,
                        source_artifact_step=_step_from_source_ref(proposal.source_ref),
                    ),
                    connection,
                )
                created_scenes.append(scene)
                updated = connection.execute(
                    """
                    UPDATE scene_proposals
                    SET status = 'accepted',
                        reviewed_at = ?,
                        applied_scene_id = ?
                    WHERE project_id = ? AND id = ? AND status = 'pending_review'
                    """,
                    (now, scene.id, project_id, proposal.id),
                )
                if updated.rowcount == 0:
                    raise SceneProposalReviewedError(
                        f"Scene proposal '{proposal.id}' changed concurrently."
                    )

            accepted_ids = [proposal.id for proposal in ordered]
            accepted_ids.extend(proposal.id for proposal in already_accepted)
            accepted = [
                self.get_scene_proposal(project_id, proposal_id, connection)
                for proposal_id in accepted_ids
            ]
            replayed_scenes = [
                self.get_scene_contract(project_id, proposal.applied_scene_id, connection)
                for proposal in already_accepted
                if proposal.applied_scene_id
            ]
        scenes = created_scenes + [scene for scene in replayed_scenes if scene]
        return scenes, [proposal for proposal in accepted if proposal is not None]


def _merge_required_canon(proposal: SceneProposal) -> str:
    """Flatten resolved canon ids plus raw names into the contract column."""
    parts = [
        part.strip()
        for part in (proposal.required_canon_ids, proposal.required_canon_raw)
        if part.strip()
    ]
    return "\n".join(parts)


def _step_from_source_ref(source_ref: str) -> int:
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
