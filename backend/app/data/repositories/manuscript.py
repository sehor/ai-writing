"""Manuscript repository: chapters, proposals, scenes and revisions.

Single-table operations only. The multi-step acceptance / restore / edit
flows that also enqueue outbox jobs live in app.data.flows so they can
coordinate the manuscript, scene and outbox repositories inside one
transaction.
"""

import json
import sqlite3

from app.data.helpers import make_record_id, utc_now
from app.models import (
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
)
from app.review.state_machine import validate_review_transition


def manuscript_chapter_from_row(row: sqlite3.Row) -> ManuscriptChapter:
    return ManuscriptChapter(
        id=row["id"],
        project_id=row["project_id"],
        sequence=row["sequence"],
        title=row["title"],
        summary=row["summary"],
    )


def manuscript_chapter_to_params(
    chapter: ManuscriptChapter,
) -> tuple[str, str, int, str, str]:
    return (
        chapter.id,
        chapter.project_id,
        chapter.sequence,
        chapter.title,
        chapter.summary,
    )


def manuscript_proposal_from_row(row: sqlite3.Row) -> ManuscriptProposal:
    return ManuscriptProposal(
        id=row["id"],
        project_id=row["project_id"],
        scene_id=row["scene_id"],
        source=row["source"],
        title=row["title"],
        content=row["content"],
        context=row["context"],
        checklist=json.loads(row["checklist_json"]),
        generation_review=json.loads(row["generation_review_json"]),
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


def manuscript_proposal_to_params(
    proposal: ManuscriptProposal,
) -> tuple[str, ...]:
    return (
        proposal.id,
        proposal.project_id,
        proposal.scene_id,
        proposal.source,
        proposal.title,
        proposal.content,
        proposal.context,
        json.dumps(proposal.checklist),
        proposal.status,
        proposal.created_at,
        proposal.reviewed_at,
        proposal.generation_review.model_dump_json() if proposal.generation_review else "null",
    )


def manuscript_scene_from_row(row: sqlite3.Row) -> ManuscriptScene:
    return ManuscriptScene(
        id=row["id"],
        project_id=row["project_id"],
        scene_id=row["scene_id"],
        proposal_id=row["proposal_id"],
        title=row["title"],
        content=row["content"],
        version=row["version"],
        accepted_at=row["accepted_at"],
    )


def manuscript_scene_to_params(
    scene: ManuscriptScene,
) -> tuple[str, str, str, str, str, str, int, str]:
    return (
        scene.id,
        scene.project_id,
        scene.scene_id,
        scene.proposal_id,
        scene.title,
        scene.content,
        scene.version,
        scene.accepted_at,
    )


def manuscript_revision_from_row(row: sqlite3.Row) -> ManuscriptRevision:
    return ManuscriptRevision(
        id=row["id"],
        project_id=row["project_id"],
        scene_id=row["scene_id"],
        proposal_id=row["proposal_id"],
        title=row["title"],
        content=row["content"],
        version=row["version"],
        created_at=row["created_at"],
    )


def manuscript_revision_to_params(
    revision: ManuscriptRevision,
) -> tuple[str, str, str, str, str, str, int, str]:
    return (
        revision.id,
        revision.project_id,
        revision.scene_id,
        revision.proposal_id,
        revision.title,
        revision.content,
        revision.version,
        revision.created_at,
    )


CHAPTER_COLUMNS = "id, project_id, sequence, title, summary"
PROPOSAL_COLUMNS = (
    "id, project_id, scene_id, source, title, content, context,"
    " checklist_json, status, created_at, reviewed_at, generation_review_json"
)
SCENE_COLUMNS = "id, project_id, scene_id, proposal_id, title, content, version, accepted_at"
REVISION_COLUMNS = "id, project_id, scene_id, proposal_id, title, content, version, created_at"


class ManuscriptRepository:
    """SQL for the four manuscript tables, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    # ------------------------------------------------------------------
    # Chapters
    # ------------------------------------------------------------------

    def list_chapters(self, project_id: str) -> list[ManuscriptChapter]:
        rows = self.connection.execute(
            f"""
            SELECT {CHAPTER_COLUMNS}
            FROM manuscript_chapters
            WHERE project_id = ?
            ORDER BY sequence
            """,
            (project_id,),
        ).fetchall()
        return [manuscript_chapter_from_row(row) for row in rows]

    def create_chapter(self, project_id: str, chapter: ManuscriptChapterCreate):
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM manuscript_chapters",
            ).fetchall()
        }
        created = ManuscriptChapter(
            id=make_record_id(
                f"{project_id}-chapter-{chapter.sequence}-{chapter.title}",
                existing_ids,
            ),
            project_id=project_id,
            **chapter.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO manuscript_chapters (
                id, project_id, sequence, title, summary
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            manuscript_chapter_to_params(created),
        )
        return created

    def update_chapter(self, project_id: str, chapter_id: str, chapter: ManuscriptChapterUpdate):
        updated = ManuscriptChapter(
            id=chapter_id,
            project_id=project_id,
            **chapter.model_dump(),
        )
        cursor = self.connection.execute(
            """
            UPDATE manuscript_chapters
            SET sequence = ?,
                title = ?,
                summary = ?
            WHERE project_id = ? AND id = ?
            """,
            (
                updated.sequence,
                updated.title,
                updated.summary,
                project_id,
                chapter_id,
            ),
        )
        return updated if cursor.rowcount else None

    def delete_chapter(self, project_id: str, chapter_id: str) -> bool:
        """Delete the chapter row; detaching contracts is the caller's job."""
        cursor = self.connection.execute(
            "DELETE FROM manuscript_chapters WHERE project_id = ? AND id = ?",
            (project_id, chapter_id),
        )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    def list_proposals(self, project_id: str) -> list[ManuscriptProposal]:
        rows = self.connection.execute(
            f"""
            SELECT {PROPOSAL_COLUMNS}
            FROM manuscript_proposals
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        return [manuscript_proposal_from_row(row) for row in rows]

    def create_proposal(self, project_id: str, proposal: ManuscriptProposalCreate):
        now = utc_now()
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM manuscript_proposals",
            ).fetchall()
        }
        created = ManuscriptProposal(
            id=make_record_id(
                f"{project_id}-proposal-{proposal.title}",
                existing_ids,
            ),
            project_id=project_id,
            status="pending_review",
            created_at=now,
            reviewed_at="",
            **proposal.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO manuscript_proposals (
                id, project_id, scene_id, source, title, content, context,
                checklist_json, status, created_at, reviewed_at, generation_review_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            manuscript_proposal_to_params(created),
        )
        return created

    def get_proposal(self, project_id: str, proposal_id: str) -> ManuscriptProposal | None:
        row = self.connection.execute(
            f"""
            SELECT {PROPOSAL_COLUMNS}
            FROM manuscript_proposals
            WHERE project_id = ? AND id = ?
            """,
            (project_id, proposal_id),
        ).fetchone()
        return manuscript_proposal_from_row(row) if row else None

    def set_proposal_status(
        self,
        *,
        project_id: str,
        proposal_id: str,
        status: str,
        reviewed_at: str,
    ) -> None:
        """Unconditional status write used by the accept flow."""
        self.connection.execute(
            """
            UPDATE manuscript_proposals
            SET status = ?,
                reviewed_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (status, reviewed_at, project_id, proposal_id),
        )

    def supersede_pending_for_scene(
        self,
        *,
        project_id: str,
        scene_id: str,
        except_proposal_id: str,
        reviewed_at: str,
    ) -> None:
        """Sibling pending proposals for an accepted scene are stale now."""
        self.connection.execute(
            """
            UPDATE manuscript_proposals
            SET status = 'superseded',
                reviewed_at = ?
            WHERE project_id = ? AND scene_id = ? AND id <> ?
              AND status = 'pending_review'
            """,
            (reviewed_at, project_id, scene_id, except_proposal_id),
        )

    def update_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: ManuscriptProposalStatus,
    ):
        """Non-accepting status change; raises on illegal transitions."""
        current = self.get_proposal(project_id, proposal_id)
        if current is None:
            return None
        if current.status == proposal_status:
            return current
        validate_review_transition(current.status, proposal_status, "Manuscript proposal")
        reviewed_at = utc_now()
        cursor = self.connection.execute(
            """
            UPDATE manuscript_proposals
            SET status = ?,
                reviewed_at = ?
            WHERE project_id = ? AND id = ? AND status = ?
            """,
            (proposal_status, reviewed_at, project_id, proposal_id, current.status),
        )
        if cursor.rowcount == 0:
            raise ValueError("Manuscript proposal changed concurrently; retry.")
        return self.get_proposal(project_id, proposal_id)

    # ------------------------------------------------------------------
    # Scenes (accepted prose per contract)
    # ------------------------------------------------------------------

    def list_scenes(self, project_id: str) -> list[ManuscriptScene]:
        rows = self.connection.execute(
            f"""
            SELECT {SCENE_COLUMNS}
            FROM manuscript_scenes
            WHERE project_id = ?
            ORDER BY accepted_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        return [manuscript_scene_from_row(row) for row in rows]

    def get_scene(self, project_id: str, scene_id: str) -> ManuscriptScene | None:
        row = self.connection.execute(
            f"""
            SELECT {SCENE_COLUMNS}
            FROM manuscript_scenes
            WHERE project_id = ? AND scene_id = ?
            """,
            (project_id, scene_id),
        ).fetchone()
        return manuscript_scene_from_row(row) if row else None

    def get_scene_version(self, project_id: str, scene_id: str) -> int | None:
        """Current scene version, or None when no scene was accepted yet."""
        row = self.connection.execute(
            """
            SELECT version
            FROM manuscript_scenes
            WHERE project_id = ? AND scene_id = ?
            """,
            (project_id, scene_id),
        ).fetchone()
        return row["version"] if row else None

    def upsert_scene(self, scene: ManuscriptScene) -> None:
        self.connection.execute(
            """
            INSERT INTO manuscript_scenes (
                id, project_id, scene_id, proposal_id, title, content,
                version, accepted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, scene_id) DO UPDATE SET
                proposal_id = excluded.proposal_id,
                title = excluded.title,
                content = excluded.content,
                version = excluded.version,
                accepted_at = excluded.accepted_at
            """,
            manuscript_scene_to_params(scene),
        )

    def update_scene_fields(
        self,
        *,
        project_id: str,
        scene_id: str,
        title: str,
        content: str,
        version: int,
        accepted_at: str,
    ) -> None:
        self.connection.execute(
            """
            UPDATE manuscript_scenes
            SET title = ?,
                content = ?,
                version = ?,
                accepted_at = ?
            WHERE project_id = ? AND scene_id = ?
            """,
            (title, content, version, accepted_at, project_id, scene_id),
        )

    def list_scene_ids(self) -> set[str]:
        """Every manuscript scene id across projects (id allocation scope)."""
        return {row["id"] for row in self.connection.execute("SELECT id FROM manuscript_scenes")}

    # ------------------------------------------------------------------
    # Revisions (immutable history)
    # ------------------------------------------------------------------

    def list_revisions(self, project_id: str) -> list[ManuscriptRevision]:
        rows = self.connection.execute(
            f"""
            SELECT {REVISION_COLUMNS}
            FROM manuscript_revisions
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        return [manuscript_revision_from_row(row) for row in rows]

    def get_revision(self, project_id: str, revision_id: str) -> ManuscriptRevision | None:
        row = self.connection.execute(
            f"""
            SELECT {REVISION_COLUMNS}
            FROM manuscript_revisions
            WHERE project_id = ? AND id = ?
            """,
            (project_id, revision_id),
        ).fetchone()
        return manuscript_revision_from_row(row) if row else None

    def insert_revision(self, revision: ManuscriptRevision) -> None:
        self.connection.execute(
            """
            INSERT INTO manuscript_revisions (
                id, project_id, scene_id, proposal_id, title, content,
                version, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            manuscript_revision_to_params(revision),
        )
        self.connection.execute(
            "UPDATE scene_contracts SET manuscript_plan_version = plan_version WHERE project_id = ? AND id = ?",
            (revision.project_id, revision.scene_id),
        )

    def list_revision_ids(self) -> set[str]:
        """Every revision id across projects (id allocation scope)."""
        return {row["id"] for row in self.connection.execute("SELECT id FROM manuscript_revisions")}

    def previous_revision_id(self, project_id: str, scene_id: str, version: int) -> str | None:
        row = self.connection.execute(
            """
            SELECT id FROM manuscript_revisions
            WHERE project_id = ? AND scene_id = ? AND version = ?
            """,
            (project_id, scene_id, version),
        ).fetchone()
        return row["id"] if row else None
