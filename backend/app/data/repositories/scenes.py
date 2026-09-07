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
        outcome=row["outcome"],
        required_canon=row["required_canon"],
        forbidden_facts=row["forbidden_facts"],
        information_delta=row["information_delta"],
        character_state_delta=row["character_state_delta"],
        story_thread_actions=row["story_thread_actions"],
        open_threads=row["open_threads"],
        source_artifact_step=row["source_artifact_step"],
        plan_version=row["plan_version"],
        source_record_step=row["source_record_step"],
        source_record_id=row["source_record_id"],
        source_record_revision_id=row["source_record_revision_id"],
    )


def scene_contract_to_params(
    scene: SceneContract,
) -> tuple:
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
        scene.outcome,
        scene.required_canon,
        scene.forbidden_facts,
        scene.information_delta,
        scene.character_state_delta,
        scene.story_thread_actions,
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
                   turning_point, outcome, required_canon, forbidden_facts,
                   information_delta, character_state_delta, story_thread_actions, open_threads,
                   source_artifact_step, plan_version, source_record_step, source_record_id, source_record_revision_id
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
                   turning_point, outcome, required_canon, forbidden_facts,
                   information_delta, character_state_delta, story_thread_actions, open_threads,
                   source_artifact_step, plan_version, source_record_step, source_record_id, source_record_revision_id
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
                turning_point, outcome, required_canon, forbidden_facts,
                information_delta, character_state_delta, story_thread_actions, open_threads,
                source_artifact_step
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                outcome = ?,
                required_canon = ?,
                forbidden_facts = ?,
                information_delta = ?,
                character_state_delta = ?,
                story_thread_actions = ?,
                open_threads = ?,
                source_artifact_step = ?,
                plan_version = plan_version + 1
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
                updated.outcome,
                updated.required_canon,
                updated.forbidden_facts,
                updated.information_delta,
                updated.character_state_delta,
                updated.story_thread_actions,
                updated.open_threads,
                updated.source_artifact_step,
                project_id,
                scene_id,
            ),
        )
        return self.get(project_id, scene_id) if cursor.rowcount else None

    def get_by_source(self, project_id: str, record_id: str) -> SceneContract | None:
        row = self.connection.execute(
            "SELECT id FROM scene_contracts WHERE project_id = ? AND source_record_step = 8 AND source_record_id = ?",
            (project_id, record_id),
        ).fetchone()
        return self.get(project_id, row["id"]) if row else None

    def bind_source(self, project_id: str, scene_id: str, record_id: str, revision_id: str) -> None:
        record = self.connection.execute(
            "SELECT id FROM snowflake_record_revisions WHERE project_id = ? AND step_number = 8 AND record_id = ? AND id = ? AND status = 'accepted'",
            (project_id, record_id, revision_id),
        ).fetchone()
        if record is None:
            raise ValueError("Source must be an accepted Step 8 record in the same project.")
        scene = self.get(project_id, scene_id)
        if scene is None or (scene.source_record_id and scene.source_record_id != record_id):
            raise ValueError("Scene is missing or already belongs to another record.")
        self.connection.execute(
            "UPDATE scene_contracts SET source_record_step = 8, source_record_id = ?, source_record_revision_id = ? WHERE project_id = ? AND id = ?",
            (record_id, revision_id, project_id, scene_id),
        )

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
            SET chapter_id = '', plan_version = plan_version + 1
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
