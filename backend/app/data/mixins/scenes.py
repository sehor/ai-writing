import sqlite3

from app.models import (
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
)
from app.data.helpers import make_record_id


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


class ScenesDataMixin:
    def list_scene_contracts(self, project_id: str) -> list[SceneContract]:
        with self.connect() as connection:
            rows = connection.execute(
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

    def get_scene_contract(self, project_id: str, scene_id: str) -> SceneContract | None:
        with self.connect() as connection:
            row = connection.execute(
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

    def create_scene_contract(self, project_id: str, scene: SceneContractCreate) -> SceneContract:
        with self.connect() as connection:
            existing_ids = {
                row["id"]
                for row in connection.execute(
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
            connection.execute(
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

    def update_scene_contract(
        self, project_id: str, scene_id: str, scene: SceneContractUpdate
    ) -> SceneContract | None:
        updated = SceneContract(
            id=scene_id,
            project_id=project_id,
            **scene.model_dump(),
        )
        with self.connect() as connection:
            cursor = connection.execute(
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

    def delete_scene_contract(self, project_id: str, scene_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM scene_contracts WHERE project_id = ? AND id = ?",
                (project_id, scene_id),
            )
        return cursor.rowcount > 0
