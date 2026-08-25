"""Project repository: the projects aggregate."""

from __future__ import annotations

import sqlite3

from app.data.helpers import make_record_id
from app.models import ProjectCreate, ProjectSummary


def make_project_id(title: str, existing_ids: set[str]) -> str:
    return make_record_id(title, existing_ids)


def project_from_row(row: sqlite3.Row) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"],
        title=row["title"],
        premise=row["premise"],
        current_step=row["current_step"],
    )


class ProjectRepository:
    """SQL for the projects table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self) -> list[ProjectSummary]:
        rows = self.connection.execute(
            """
            SELECT id, title, premise, current_step
            FROM projects
            ORDER BY rowid
            """
        ).fetchall()
        return [project_from_row(row) for row in rows]

    def create(self, project: ProjectCreate) -> ProjectSummary:
        existing_ids = {
            row["id"] for row in self.connection.execute("SELECT id FROM projects").fetchall()
        }
        created = ProjectSummary(
            id=make_project_id(project.title, existing_ids),
            title=project.title,
            premise=project.premise,
            current_step=1,
        )
        self.connection.execute(
            """
            INSERT INTO projects (id, title, premise, current_step)
            VALUES (?, ?, ?, ?)
            """,
            (
                created.id,
                created.title,
                created.premise,
                created.current_step,
            ),
        )
        return created

    def get(self, project_id: str) -> ProjectSummary | None:
        row = self.connection.execute(
            """
            SELECT id, title, premise, current_step
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()
        return project_from_row(row) if row else None

    def exists(self, project_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM projects WHERE id = ? LIMIT 1",
            (project_id,),
        ).fetchone()
        return row is not None

    def advance_current_step(self, project_id: str, completed_step: int) -> ProjectSummary | None:
        next_step = min(completed_step + 1, 10)
        self.connection.execute(
            """
            UPDATE projects
            SET current_step = MAX(current_step, ?)
            WHERE id = ?
            """,
            (next_step, project_id),
        )
        row = self.connection.execute(
            "SELECT id, title, premise, current_step FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return project_from_row(row) if row else None
