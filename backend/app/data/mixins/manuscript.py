import json
import sqlite3

from app.models import (
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
)
from app.data.helpers import make_record_id, utc_now


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
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


def manuscript_proposal_to_params(
    proposal: ManuscriptProposal,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str]:
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


class ManuscriptDataMixin:
    def list_manuscript_chapters(self, project_id: str) -> list[ManuscriptChapter]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, sequence, title, summary
                FROM manuscript_chapters
                WHERE project_id = ?
                ORDER BY sequence
                """,
                (project_id,),
            ).fetchall()
        return [manuscript_chapter_from_row(row) for row in rows]

    def create_manuscript_chapter(
        self, project_id: str, chapter: ManuscriptChapterCreate
    ) -> ManuscriptChapter:
        with self.connect() as connection:
            existing_ids = {
                row["id"]
                for row in connection.execute(
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
            connection.execute(
                """
                INSERT INTO manuscript_chapters (
                    id, project_id, sequence, title, summary
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                manuscript_chapter_to_params(created),
            )
        return created

    def update_manuscript_chapter(
        self, project_id: str, chapter_id: str, chapter: ManuscriptChapterUpdate
    ) -> ManuscriptChapter | None:
        updated = ManuscriptChapter(
            id=chapter_id,
            project_id=project_id,
            **chapter.model_dump(),
        )
        with self.connect() as connection:
            cursor = connection.execute(
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

    def delete_manuscript_chapter(self, project_id: str, chapter_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM manuscript_chapters WHERE project_id = ? AND id = ?",
                (project_id, chapter_id),
            )
            if cursor.rowcount:
                connection.execute(
                    """
                    UPDATE scene_contracts
                    SET chapter_id = ''
                    WHERE project_id = ? AND chapter_id = ?
                    """,
                    (project_id, chapter_id),
                )
        return cursor.rowcount > 0

    def list_manuscript_proposals(self, project_id: str) -> list[ManuscriptProposal]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, scene_id, source, title, content, context,
                       checklist_json, status, created_at, reviewed_at
                FROM manuscript_proposals
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [manuscript_proposal_from_row(row) for row in rows]

    def create_manuscript_proposal(
        self, project_id: str, proposal: ManuscriptProposalCreate
    ) -> ManuscriptProposal:
        now = utc_now()
        with self.connect() as connection:
            existing_ids = {
                row["id"]
                for row in connection.execute(
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
            connection.execute(
                """
                INSERT INTO manuscript_proposals (
                    id, project_id, scene_id, source, title, content, context,
                    checklist_json, status, created_at, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                manuscript_proposal_to_params(created),
            )
        return created

    def update_manuscript_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: ManuscriptProposalStatus,
    ) -> ManuscriptProposal | None:
        reviewed_at = utc_now() if proposal_status != "pending_review" else ""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, scene_id, source, title, content, context,
                       checklist_json, status, created_at, reviewed_at
                FROM manuscript_proposals
                WHERE project_id = ? AND id = ?
                """,
                (project_id, proposal_id),
            ).fetchone()
            if row is None:
                return None
            current = manuscript_proposal_from_row(row)
            if current.status == proposal_status:
                return current
            if current.status != "pending_review":
                return None
            cursor = connection.execute(
                """
                UPDATE manuscript_proposals
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
                SELECT id, project_id, scene_id, source, title, content, context,
                       checklist_json, status, created_at, reviewed_at
                FROM manuscript_proposals
                WHERE project_id = ? AND id = ?
                """,
                (project_id, proposal_id),
            ).fetchone()
        return manuscript_proposal_from_row(row) if row else None

    def get_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptProposal | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, scene_id, source, title, content, context,
                       checklist_json, status, created_at, reviewed_at
                FROM manuscript_proposals
                WHERE project_id = ? AND id = ?
                """,
                (project_id, proposal_id),
            ).fetchone()
        return manuscript_proposal_from_row(row) if row else None

    def list_manuscript_scenes(self, project_id: str) -> list[ManuscriptScene]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, accepted_at
                FROM manuscript_scenes
                WHERE project_id = ?
                ORDER BY accepted_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [manuscript_scene_from_row(row) for row in rows]

    def list_manuscript_revisions(self, project_id: str) -> list[ManuscriptRevision]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, created_at
                FROM manuscript_revisions
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [manuscript_revision_from_row(row) for row in rows]

    def get_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptRevision | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, created_at
                FROM manuscript_revisions
                WHERE project_id = ? AND id = ?
                """,
                (project_id, revision_id),
            ).fetchone()
        return manuscript_revision_from_row(row) if row else None

    def accept_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptScene | None:
        now = utc_now()
        with self.connect() as connection:
            proposal_row = connection.execute(
                """
                SELECT id, project_id, scene_id, source, title, content, context,
                       checklist_json, status, created_at, reviewed_at
                FROM manuscript_proposals
                WHERE project_id = ? AND id = ?
                """,
                (project_id, proposal_id),
            ).fetchone()
            if proposal_row is None:
                return None
            proposal = manuscript_proposal_from_row(proposal_row)
            if proposal.status == "accepted":
                return self.get_manuscript_scene(project_id, proposal.scene_id)
            if proposal.status != "pending_review":
                return None
            current_row = connection.execute(
                """
                SELECT version
                FROM manuscript_scenes
                WHERE project_id = ? AND scene_id = ?
                """,
                (project_id, proposal.scene_id),
            ).fetchone()
            version = current_row["version"] + 1 if current_row else 1
            scene = ManuscriptScene(
                id=make_record_id(
                    f"{project_id}-manuscript-{proposal.scene_id}",
                    {
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM manuscript_scenes",
                        ).fetchall()
                    },
                )
                if current_row is None
                else f"manuscript-{proposal.scene_id}",
                project_id=project_id,
                scene_id=proposal.scene_id,
                proposal_id=proposal.id,
                title=proposal.title,
                content=proposal.content,
                version=version,
                accepted_at=now,
            )
            revision = ManuscriptRevision(
                id=make_record_id(
                    f"{project_id}-revision-{proposal.scene_id}-v{version}",
                    {
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM manuscript_revisions",
                        ).fetchall()
                    },
                ),
                project_id=project_id,
                scene_id=proposal.scene_id,
                proposal_id=proposal.id,
                title=proposal.title,
                content=proposal.content,
                version=version,
                created_at=now,
            )
            connection.execute(
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
            connection.execute(
                """
                INSERT INTO manuscript_revisions (
                    id, project_id, scene_id, proposal_id, title, content,
                    version, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                manuscript_revision_to_params(revision),
            )
            connection.execute(
                """
                UPDATE manuscript_proposals
                SET status = ?,
                    reviewed_at = ?
                WHERE project_id = ? AND id = ?
                """,
                ("accepted", now, project_id, proposal_id),
            )
        return self.get_manuscript_scene(project_id, proposal.scene_id)

    def get_manuscript_scene(self, project_id: str, scene_id: str) -> ManuscriptScene | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, accepted_at
                FROM manuscript_scenes
                WHERE project_id = ? AND scene_id = ?
                """,
                (project_id, scene_id),
            ).fetchone()
        return manuscript_scene_from_row(row) if row else None

    def restore_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptScene | None:
        now = utc_now()
        with self.connect() as connection:
            revision_row = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, created_at
                FROM manuscript_revisions
                WHERE project_id = ? AND id = ?
                """,
                (project_id, revision_id),
            ).fetchone()
            if revision_row is None:
                return None
            source_revision = manuscript_revision_from_row(revision_row)
            current_row = connection.execute(
                """
                SELECT version
                FROM manuscript_scenes
                WHERE project_id = ? AND scene_id = ?
                """,
                (project_id, source_revision.scene_id),
            ).fetchone()
            version = current_row["version"] + 1 if current_row else 1
            scene = ManuscriptScene(
                id=make_record_id(
                    f"{project_id}-manuscript-{source_revision.scene_id}",
                    {
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM manuscript_scenes",
                        ).fetchall()
                    },
                )
                if current_row is None
                else f"{project_id}-manuscript-{source_revision.scene_id}",
                project_id=project_id,
                scene_id=source_revision.scene_id,
                proposal_id=source_revision.proposal_id,
                title=source_revision.title,
                content=source_revision.content,
                version=version,
                accepted_at=now,
            )
            restored_revision = ManuscriptRevision(
                id=make_record_id(
                    f"{project_id}-revision-{source_revision.scene_id}-v{version}",
                    {
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM manuscript_revisions",
                        ).fetchall()
                    },
                ),
                project_id=project_id,
                scene_id=source_revision.scene_id,
                proposal_id=source_revision.proposal_id,
                title=source_revision.title,
                content=source_revision.content,
                version=version,
                created_at=now,
            )
            connection.execute(
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
            connection.execute(
                """
                INSERT INTO manuscript_revisions (
                    id, project_id, scene_id, proposal_id, title, content,
                    version, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                manuscript_revision_to_params(restored_revision),
            )
        return self.get_manuscript_scene(project_id, source_revision.scene_id)

    def update_manuscript_scene(
        self, project_id: str, scene_id: str, update: ManuscriptSceneUpdate
    ) -> ManuscriptScene | None:
        now = utc_now()
        with self.connect() as connection:
            current_row = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, accepted_at
                FROM manuscript_scenes
                WHERE project_id = ? AND scene_id = ?
                """,
                (project_id, scene_id),
            ).fetchone()
            if current_row is None:
                return None
            current_scene = manuscript_scene_from_row(current_row)
            version = current_scene.version + 1
            updated_scene = ManuscriptScene(
                id=current_scene.id,
                project_id=project_id,
                scene_id=scene_id,
                proposal_id=current_scene.proposal_id,
                title=update.title,
                content=update.content,
                version=version,
                accepted_at=now,
            )
            revision = ManuscriptRevision(
                id=make_record_id(
                    f"{project_id}-revision-{scene_id}-v{version}",
                    {
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM manuscript_revisions",
                        ).fetchall()
                    },
                ),
                project_id=project_id,
                scene_id=scene_id,
                proposal_id=current_scene.proposal_id,
                title=update.title,
                content=update.content,
                version=version,
                created_at=now,
            )
            connection.execute(
                """
                UPDATE manuscript_scenes
                SET title = ?,
                    content = ?,
                    version = ?,
                    accepted_at = ?
                WHERE project_id = ? AND scene_id = ?
                """,
                (
                    updated_scene.title,
                    updated_scene.content,
                    updated_scene.version,
                    updated_scene.accepted_at,
                    project_id,
                    scene_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO manuscript_revisions (
                    id, project_id, scene_id, proposal_id, title, content,
                    version, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                manuscript_revision_to_params(revision),
            )
            row = connection.execute(
                """
                SELECT id, project_id, scene_id, proposal_id, title, content,
                       version, accepted_at
                FROM manuscript_scenes
                WHERE project_id = ? AND scene_id = ?
                """,
                (project_id, scene_id),
            ).fetchone()
        return manuscript_scene_from_row(row) if row else None
