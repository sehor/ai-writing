"""Scene repository: Scene Contracts (the accepted planning rows)."""

from __future__ import annotations

import sqlite3

from app.data.helpers import make_record_id
from app.models import SceneContract, SceneContractCreate, SceneContractUpdate


def scene_contract_from_row(row: sqlite3.Row) -> SceneContract:
    return SceneContract(
        id=row["id"],
        project_id=row["project_id"],
        chapter_id=row["chapter_id"],
        sequence=row["sequence"],
        title=row["title"],
        pov=row["pov"],
        goal=row["goal"],
        conflict=row["conflict"],
        turning_point=row["turning_point"],
        required_canon=row["required_canon"],
        forbidden_facts=row["forbidden_facts"],
        open_threads=row["open_threads"],
        source_artifact_step=row["source_artifact_step"],
    )


def scene_contract_to_params(
    scene: SceneContract,
) -> tuple[str, str, str, int, str, str, str, str, str, str, str, str, int]:
    return (
        scene.id,
        scene.project_id,
        scene.chapter_id,
        scene.sequence,
        scene.title,
        scene.pov,
        scene.goal,
        scene.conflict,
        scene.turning_point,
        scene.required_canon,
        scene.forbidden_facts,
        scene.open_threads,
        scene.source_artifact_step,
    )


class SceneRepository:
    """SQL for the scene_contracts table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self, project_id: str) -> list[SceneContract]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, chapter_id, sequence, title, pov, goal, conflict,
                   turning_point, required_canon, forbidden_facts, open_threads,
                   source_artifact_step
            FROM scene_contracts
            WHERE project_id = ?
            ORDER BY sequence
            """,
            (project_id,),
        ).fetchall()
        return [scene_contract_from_row(row) for row in rows]

    def get(self, project_id: str, scene_id: str) -> SceneContract | None:
        row = self.connection.execute(
            """
            SELECT id, project_id, chapter_id, sequence, title, pov, goal, conflict,
                   turning_point, required_canon, forbidden_facts, open_threads,
                   source_artifact_step
            FROM scene_contracts
            WHERE project_id = ? AND id = ?
            """,
            (project_id, scene_id),
        ).fetchone()
        return scene_contract_from_row(row) if row else None

    def insert(self, project_id: str, scene: SceneContractCreate) -> SceneContract:
        """Create one contract inside the caller's transaction.

        Shared by the plain CRUD route and the P1-05 batch acceptance of
        parsed Step 8 scene proposals.
        """
        existing_ids = {
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM scene_contracts",
            ).fetchall()
        }
        created = SceneContract(
            id=make_record_id(
                f"{project_id}-s{scene.sequence}-{scene.title}",
                existing_ids,
            ),
            project_id=project_id,
            **scene.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO scene_contracts (
                id, project_id, chapter_id, sequence, title, pov, goal, conflict,
                turning_point, required_canon, forbidden_facts, open_threads,
                source_artifact_step
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            scene_contract_to_params(created),
        )
        return created

    def update(self, project_id: str, scene_id: str, scene: SceneContractUpdate):
        updated = SceneContract(
            id=scene_id,
            project_id=project_id,
            **scene.model_dump(),
        )
        cursor = self.connection.execute(
            """
            UPDATE scene_contracts
            SET sequence = ?,
                chapter_id = ?,
                title = ?,
                pov = ?,
                goal = ?,
                conflict = ?,
                turning_point = ?,
                required_canon = ?,
                forbidden_facts = ?,
                open_threads = ?,
                source_artifact_step = ?
            WHERE project_id = ? AND id = ?
            """,
            (
                updated.sequence,
                updated.chapter_id,
                updated.title,
                updated.pov,
                updated.goal,
                updated.conflict,
                updated.turning_point,
                updated.required_canon,
                updated.forbidden_facts,
                updated.open_threads,
                updated.source_artifact_step,
                project_id,
                scene_id,
            ),
        )
        return updated if cursor.rowcount else None

    def delete(self, project_id: str, scene_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM scene_contracts WHERE project_id = ? AND id = ?",
            (project_id, scene_id),
        )
        return cursor.rowcount > 0

    def clear_chapter_reference(self, project_id: str, chapter_id: str) -> None:
        """Detach contracts from a deleted chapter (keeps the scenes)."""
        self.connection.execute(
            """
            UPDATE scene_contracts
            SET chapter_id = ''
            WHERE project_id = ? AND chapter_id = ?
            """,
            (project_id, chapter_id),
        )

    def get_sequence(self, project_id: str, scene_id: str) -> int | None:
        row = self.connection.execute(
            """
            SELECT sequence FROM scene_contracts
            WHERE project_id = ? AND id = ?
            """,
            (project_id, scene_id),
        ).fetchone()
        return row["sequence"] if row else None

    def list_sequences(self, project_id: str) -> set[int]:
        rows = self.connection.execute(
            "SELECT sequence FROM scene_contracts WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        return {row["sequence"] for row in rows}
