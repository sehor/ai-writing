from __future__ import annotations

import sqlite3

from app.data.helpers import make_record_id
from app.models import (
    CharacterKnowledge,
    CharacterKnowledgeCreate,
    StoryFact,
    StoryFactCreate,
    StoryThread,
    StoryThreadCreate,
    StoryThreadEvent,
    StoryThreadEventCreate,
)


def _fact_from_row(row: sqlite3.Row) -> StoryFact:
    return StoryFact(
        id=row["id"],
        project_id=row["project_id"],
        subject=row["subject"],
        predicate=row["predicate"],
        value=row["value"],
        valid_from_scene=row["valid_from_scene"],
        valid_to_scene=row["valid_to_scene"],
        reader_visible_from=row["reader_visible_from"],
        source_ref=row["source_ref"],
        status=row["status"],
    )


def _thread_from_row(row: sqlite3.Row) -> StoryThread:
    return StoryThread(
        id=row["id"],
        project_id=row["project_id"],
        thread_type=row["thread_type"],
        title=row["title"],
        status=row["status"],
        planted_at=row["planted_at"],
        target_payoff_from=row["target_payoff_from"],
        target_payoff_to=row["target_payoff_to"],
        importance=row["importance"],
        reveal_constraints=row["reveal_constraints"],
    )


def _event_from_row(row: sqlite3.Row) -> StoryThreadEvent:
    return StoryThreadEvent(
        id=row["id"],
        project_id=row["project_id"],
        thread_id=row["thread_id"],
        scene_id=row["scene_id"],
        action=row["action"],
        note=row["note"],
    )


class NarrativeRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create_fact(self, project_id: str, fact: StoryFactCreate) -> StoryFact:
        if fact.valid_to_scene is not None and fact.valid_to_scene < fact.valid_from_scene:
            raise ValueError("valid_to_scene cannot be before valid_from_scene")
        existing_ids = {row["id"] for row in self.connection.execute("SELECT id FROM story_facts")}
        created = StoryFact(
            id=make_record_id(
                f"{project_id}-{fact.subject}-{fact.predicate}-{fact.valid_from_scene}", existing_ids
            ),
            project_id=project_id,
            **fact.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO story_facts (
                id, project_id, subject, predicate, value, valid_from_scene,
                valid_to_scene, reader_visible_from, source_ref, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created.id,
                project_id,
                created.subject,
                created.predicate,
                created.value,
                created.valid_from_scene,
                created.valid_to_scene,
                created.reader_visible_from,
                created.source_ref,
                created.status,
            ),
        )
        return created

    def list_facts(self, project_id: str) -> list[StoryFact]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, subject, predicate, value, valid_from_scene,
                   valid_to_scene, reader_visible_from, source_ref, status
            FROM story_facts
            WHERE project_id = ?
            ORDER BY valid_from_scene, subject, predicate, id
            """,
            (project_id,),
        ).fetchall()
        return [_fact_from_row(row) for row in rows]

    def facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, subject, predicate, value, valid_from_scene,
                   valid_to_scene, reader_visible_from, source_ref, status
            FROM story_facts
            WHERE project_id = ?
              AND status = 'confirmed'
              AND valid_from_scene <= ?
              AND (valid_to_scene IS NULL OR valid_to_scene >= ?)
            ORDER BY subject, predicate, valid_from_scene DESC, id
            """,
            (project_id, scene_position, scene_position),
        ).fetchall()
        return [_fact_from_row(row) for row in rows]

    def set_character_knowledge(
        self,
        project_id: str,
        fact_id: str,
        knowledge: CharacterKnowledgeCreate,
    ) -> CharacterKnowledge:
        if not self.connection.execute(
            "SELECT 1 FROM story_facts WHERE project_id = ? AND id = ?",
            (project_id, fact_id),
        ).fetchone():
            raise LookupError("Story fact not found")
        self.connection.execute(
            """
            INSERT INTO story_fact_character_knowledge (
                project_id, fact_id, character, known_from_scene
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, fact_id, character)
            DO UPDATE SET known_from_scene = excluded.known_from_scene
            """,
            (project_id, fact_id, knowledge.character, knowledge.known_from_scene),
        )
        return CharacterKnowledge(
            project_id=project_id,
            fact_id=fact_id,
            **knowledge.model_dump(),
        )

    def reader_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
        return [
            fact
            for fact in self.facts_at(project_id, scene_position)
            if fact.reader_visible_from is not None and fact.reader_visible_from <= scene_position
        ]

    def character_facts_at(
        self,
        project_id: str,
        character: str,
        scene_position: int,
    ) -> list[StoryFact]:
        rows = self.connection.execute(
            """
            SELECT f.id, f.project_id, f.subject, f.predicate, f.value,
                   f.valid_from_scene, f.valid_to_scene, f.reader_visible_from,
                   f.source_ref, f.status
            FROM story_facts f
            JOIN story_fact_character_knowledge k
              ON k.project_id = f.project_id AND k.fact_id = f.id
            WHERE f.project_id = ?
              AND lower(k.character) = lower(?)
              AND k.known_from_scene <= ?
              AND f.status = 'confirmed'
              AND f.valid_from_scene <= ?
              AND (f.valid_to_scene IS NULL OR f.valid_to_scene >= ?)
            ORDER BY f.subject, f.predicate, f.valid_from_scene DESC, f.id
            """,
            (project_id, character, scene_position, scene_position, scene_position),
        ).fetchall()
        return [_fact_from_row(row) for row in rows]

    def create_thread(self, project_id: str, thread: StoryThreadCreate) -> StoryThread:
        if (
            thread.target_payoff_from is not None
            and thread.target_payoff_to is not None
            and thread.target_payoff_to < thread.target_payoff_from
        ):
            raise ValueError("target_payoff_to cannot be before target_payoff_from")
        existing_ids = {row["id"] for row in self.connection.execute("SELECT id FROM story_threads")}
        created = StoryThread(
            id=make_record_id(f"{project_id}-{thread.thread_type}-{thread.title}", existing_ids),
            project_id=project_id,
            **thread.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO story_threads (
                id, project_id, thread_type, title, status, planted_at,
                target_payoff_from, target_payoff_to, importance, reveal_constraints
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created.id,
                project_id,
                created.thread_type,
                created.title,
                created.status,
                created.planted_at,
                created.target_payoff_from,
                created.target_payoff_to,
                created.importance,
                created.reveal_constraints,
            ),
        )
        return created

    def list_threads(self, project_id: str) -> list[StoryThread]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, thread_type, title, status, planted_at,
                   target_payoff_from, target_payoff_to, importance, reveal_constraints
            FROM story_threads
            WHERE project_id = ?
            ORDER BY importance DESC, COALESCE(planted_at, 9999), title
            """,
            (project_id,),
        ).fetchall()
        return [_thread_from_row(row) for row in rows]

    def set_thread_status(self, project_id: str, thread_id: str, status: str) -> StoryThread | None:
        cursor = self.connection.execute(
            "UPDATE story_threads SET status = ? WHERE project_id = ? AND id = ?",
            (status, project_id, thread_id),
        )
        if cursor.rowcount == 0:
            return None
        row = self.connection.execute(
            """
            SELECT id, project_id, thread_type, title, status, planted_at,
                   target_payoff_from, target_payoff_to, importance, reveal_constraints
            FROM story_threads
            WHERE project_id = ? AND id = ?
            """,
            (project_id, thread_id),
        ).fetchone()
        return _thread_from_row(row) if row else None

    def add_thread_event(
        self,
        project_id: str,
        thread_id: str,
        event: StoryThreadEventCreate,
    ) -> StoryThreadEvent:
        if not self.connection.execute(
            "SELECT 1 FROM story_threads WHERE project_id = ? AND id = ?",
            (project_id, thread_id),
        ).fetchone():
            raise LookupError("Story thread not found")
        existing_ids = {
            row["id"] for row in self.connection.execute("SELECT id FROM story_thread_events")
        }
        created = StoryThreadEvent(
            id=make_record_id(f"{thread_id}-{event.scene_id}-{event.action}", existing_ids),
            project_id=project_id,
            thread_id=thread_id,
            **event.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO story_thread_events (id, project_id, thread_id, scene_id, action, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created.id,
                project_id,
                thread_id,
                created.scene_id,
                created.action,
                created.note,
            ),
        )
        scene_row = self.connection.execute(
            "SELECT sequence FROM scene_contracts WHERE project_id = ? AND id = ?",
            (project_id, created.scene_id),
        ).fetchone()
        scene_sequence = int(scene_row["sequence"]) if scene_row else None
        if created.action == "payoff":
            self.connection.execute(
                "UPDATE story_threads SET status = 'paid_off' WHERE project_id = ? AND id = ?",
                (project_id, thread_id),
            )
        elif created.action == "plant":
            self.connection.execute(
                """
                UPDATE story_threads
                SET status = 'planted', planted_at = COALESCE(planted_at, ?)
                WHERE project_id = ? AND id = ?
                """,
                (scene_sequence, project_id, thread_id),
            )
        elif created.action in {"reinforce", "misdirect", "escalate", "partial_payoff"}:
            self.connection.execute(
                """
                UPDATE story_threads
                SET status = CASE WHEN status IN ('planned', 'planted', 'dormant')
                                  THEN 'developing' ELSE status END
                WHERE project_id = ? AND id = ?
                """,
                (project_id, thread_id),
            )
        return created

    def list_thread_events(self, project_id: str, thread_id: str) -> list[StoryThreadEvent]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, thread_id, scene_id, action, note
            FROM story_thread_events
            WHERE project_id = ? AND thread_id = ?
            ORDER BY rowid
            """,
            (project_id, thread_id),
        ).fetchall()
        return [_event_from_row(row) for row in rows]
