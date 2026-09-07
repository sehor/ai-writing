"""Optional organization links. Deleting a volume never deletes author content."""

import sqlite3
from uuid import uuid4
from app.domain_models.volume import (
    ManuscriptVolume,
    ManuscriptVolumeCreate,
    ChapterVolumeMembership,
)
from app.errors import ResourceNotFoundError


class VolumeRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self, project_id: str) -> list[ManuscriptVolume]:
        rows = self.connection.execute(
            "SELECT id, project_id, sequence, title FROM manuscript_volumes WHERE project_id = ? ORDER BY sequence, id",
            (project_id,),
        ).fetchall()
        members: dict[str, list[str]] = {}
        for row in self.connection.execute(
            "SELECT m.volume_id, m.chapter_id FROM manuscript_volume_chapters m "
            "JOIN manuscript_chapters c ON c.project_id = m.project_id AND c.id = m.chapter_id "
            "WHERE m.project_id = ? ORDER BY c.sequence, c.id",
            (project_id,),
        ):
            members.setdefault(row["volume_id"], []).append(row["chapter_id"])
        return [
            ManuscriptVolume(**dict(row), chapter_ids=members.get(row["id"], [])) for row in rows
        ]

    def create(self, project_id: str, create: ManuscriptVolumeCreate) -> ManuscriptVolume:
        volume = ManuscriptVolume(
            id=f"volume-{uuid4().hex}", project_id=project_id, **create.model_dump()
        )
        self.connection.execute(
            "INSERT INTO manuscript_volumes (id, project_id, sequence, title) VALUES (?, ?, ?, ?)",
            (volume.id, project_id, volume.sequence, volume.title),
        )
        return volume

    def update(
        self, project_id: str, volume_id: str, update: ManuscriptVolumeCreate
    ) -> ManuscriptVolume:
        cursor = self.connection.execute(
            "UPDATE manuscript_volumes SET sequence = ?, title = ? WHERE project_id = ? AND id = ?",
            (update.sequence, update.title, project_id, volume_id),
        )
        if not cursor.rowcount:
            raise ResourceNotFoundError("Manuscript volume not found.")
        return next(volume for volume in self.list(project_id) if volume.id == volume_id)

    def delete(self, project_id: str, volume_id: str) -> bool:
        # Only membership rows cascade. Chapters, scenes and revisions are not children of this row.
        return bool(
            self.connection.execute(
                "DELETE FROM manuscript_volumes WHERE project_id = ? AND id = ?",
                (project_id, volume_id),
            ).rowcount
        )

    def assign(self, project_id: str, chapter_id: str, volume_id: str) -> ChapterVolumeMembership:
        if not self.connection.execute(
            "SELECT 1 FROM manuscript_chapters WHERE project_id = ? AND id = ?",
            (project_id, chapter_id),
        ).fetchone():
            raise ResourceNotFoundError("Chapter not found in this project.")
        if volume_id:
            if not self.connection.execute(
                "SELECT 1 FROM manuscript_volumes WHERE project_id = ? AND id = ?",
                (project_id, volume_id),
            ).fetchone():
                raise ResourceNotFoundError("Volume not found in this project.")
            self.connection.execute(
                "INSERT INTO manuscript_volume_chapters (project_id, chapter_id, volume_id) VALUES (?, ?, ?) "
                "ON CONFLICT(project_id, chapter_id) DO UPDATE SET volume_id = excluded.volume_id",
                (project_id, chapter_id, volume_id),
            )
        else:
            self.connection.execute(
                "DELETE FROM manuscript_volume_chapters WHERE project_id = ? AND chapter_id = ?",
                (project_id, chapter_id),
            )
        return ChapterVolumeMembership(chapter_id=chapter_id, volume_id=volume_id)
