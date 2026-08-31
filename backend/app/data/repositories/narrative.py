from __future__ import annotations

import sqlite3

from app.data.helpers import make_record_id
from app.models import (
    CharacterKnowledge,
    CharacterKnowledgeCreate,
    KnowledgeState,
    KnowledgeStateCreate,
    NarrativeRelation,
    NarrativeRelationCreate,
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


def _knowledge_state_from_row(row: sqlite3.Row) -> KnowledgeState:
    return KnowledgeState(
        id=row["id"],
        project_id=row["project_id"],
        fact_id=row["fact_id"],
        scope=row["scope"],
        character=row["character"],
        known_from_scene=row["known_from_scene"],
        source_ref=row["source_ref"],
        status=row["status"],
    )


def _relation_from_row(row: sqlite3.Row) -> NarrativeRelation:
    return NarrativeRelation(
        id=row["id"],
        project_id=row["project_id"],
        source=row["source"],
        target=row["target"],
        relation=row["relation"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        confidence=row["confidence"],
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
                f"{project_id}-{fact.subject}-{fact.predicate}-{fact.valid_from_scene}",
                existing_ids,
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
        self.set_knowledge_state(
            project_id,
            created.id,
            KnowledgeStateCreate(
                scope="world_truth",
                known_from_scene=created.valid_from_scene,
                source_ref=created.source_ref,
                status=created.status,
            ),
        )
        if created.reader_visible_from is not None:
            self.set_knowledge_state(
                project_id,
                created.id,
                KnowledgeStateCreate(
                    scope="reader_knowledge",
                    known_from_scene=created.reader_visible_from,
                    source_ref=created.source_ref,
                    status=created.status,
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

    def set_knowledge_state(
        self,
        project_id: str,
        fact_id: str,
        knowledge: KnowledgeStateCreate,
    ) -> KnowledgeState:
        fact_row = self.connection.execute(
            "SELECT source_ref, status FROM story_facts WHERE project_id = ? AND id = ?",
            (project_id, fact_id),
        ).fetchone()
        if not fact_row:
            raise LookupError("Story fact not found")
        existing = self.connection.execute(
            """
            SELECT id FROM knowledge_states
            WHERE project_id = ? AND fact_id = ? AND scope = ? AND character = ?
            """,
            (project_id, fact_id, knowledge.scope, knowledge.character),
        ).fetchone()
        if existing:
            state_id = existing["id"]
        else:
            existing_ids = {
                row["id"] for row in self.connection.execute("SELECT id FROM knowledge_states")
            }
            state_id = make_record_id(
                f"knowledge-{fact_id}-{knowledge.scope}-{knowledge.character}", existing_ids
            )
        source_ref = knowledge.source_ref or fact_row["source_ref"]
        created = KnowledgeState(
            id=state_id,
            project_id=project_id,
            fact_id=fact_id,
            **knowledge.model_dump(exclude={"source_ref"}),
            source_ref=source_ref,
        )
        self.connection.execute(
            """
            INSERT INTO knowledge_states (
                id, project_id, fact_id, scope, character, known_from_scene, source_ref, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, fact_id, scope, character)
            DO UPDATE SET known_from_scene = excluded.known_from_scene,
                          source_ref = excluded.source_ref,
                          status = excluded.status
            """,
            (
                created.id,
                project_id,
                fact_id,
                created.scope,
                created.character,
                created.known_from_scene,
                created.source_ref,
                created.status,
            ),
        )
        if created.scope == "reader_knowledge":
            self.connection.execute(
                "UPDATE story_facts SET reader_visible_from = ? WHERE project_id = ? AND id = ?",
                (created.known_from_scene, project_id, fact_id),
            )
        elif created.scope == "character_knowledge":
            self.connection.execute(
                """
                INSERT INTO story_fact_character_knowledge (
                    project_id, fact_id, character, known_from_scene
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, fact_id, character)
                DO UPDATE SET known_from_scene = excluded.known_from_scene
                """,
                (project_id, fact_id, created.character, created.known_from_scene),
            )
        return created

    def list_knowledge_states(self, project_id: str, fact_id: str) -> list[KnowledgeState]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, fact_id, scope, character, known_from_scene, source_ref, status
            FROM knowledge_states
            WHERE project_id = ? AND fact_id = ?
            ORDER BY scope, lower(character), known_from_scene, id
            """,
            (project_id, fact_id),
        ).fetchall()
        return [_knowledge_state_from_row(row) for row in rows]

    def set_character_knowledge(
        self,
        project_id: str,
        fact_id: str,
        knowledge: CharacterKnowledgeCreate,
    ) -> CharacterKnowledge:
        state = self.set_knowledge_state(
            project_id,
            fact_id,
            KnowledgeStateCreate(
                scope="character_knowledge",
                character=knowledge.character,
                known_from_scene=knowledge.known_from_scene,
            ),
        )
        return CharacterKnowledge(
            project_id=project_id,
            fact_id=fact_id,
            character=state.character,
            known_from_scene=state.known_from_scene,
        )

    def reader_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
        rows = self.connection.execute(
            """
            SELECT f.id, f.project_id, f.subject, f.predicate, f.value,
                   f.valid_from_scene, f.valid_to_scene, f.reader_visible_from,
                   f.source_ref, f.status
            FROM story_facts f
            JOIN knowledge_states k
              ON k.project_id = f.project_id AND k.fact_id = f.id
            WHERE f.project_id = ?
              AND k.scope = 'reader_knowledge'
              AND k.known_from_scene <= ?
              AND k.status = 'confirmed'
              AND f.status = 'confirmed'
              AND f.valid_from_scene <= ?
              AND (f.valid_to_scene IS NULL OR f.valid_to_scene >= ?)
            ORDER BY f.subject, f.predicate, f.valid_from_scene DESC, f.id
            """,
            (project_id, scene_position, scene_position, scene_position),
        ).fetchall()
        return [_fact_from_row(row) for row in rows]

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
            JOIN knowledge_states k
              ON k.project_id = f.project_id AND k.fact_id = f.id
            WHERE f.project_id = ?
              AND k.scope = 'character_knowledge'
              AND lower(k.character) = lower(?)
              AND k.known_from_scene <= ?
              AND k.status = 'confirmed'
              AND f.status = 'confirmed'
              AND f.valid_from_scene <= ?
              AND (f.valid_to_scene IS NULL OR f.valid_to_scene >= ?)
            ORDER BY f.subject, f.predicate, f.valid_from_scene DESC, f.id
            """,
            (project_id, character, scene_position, scene_position, scene_position),
        ).fetchall()
        return [_fact_from_row(row) for row in rows]

    def create_relation(
        self,
        project_id: str,
        relation: NarrativeRelationCreate,
    ) -> NarrativeRelation:
        if relation.valid_to is not None and relation.valid_to < relation.valid_from:
            raise ValueError("valid_to cannot be before valid_from")
        existing_ids = {
            row["id"] for row in self.connection.execute("SELECT id FROM narrative_relations")
        }
        created = NarrativeRelation(
            id=make_record_id(
                f"{project_id}-{relation.source}-{relation.relation}-{relation.target}-{relation.valid_from}",
                existing_ids,
            ),
            project_id=project_id,
            **relation.model_dump(),
        )
        self.connection.execute(
            """
            INSERT INTO narrative_relations (
                id, project_id, source, target, relation, valid_from, valid_to,
                confidence, source_ref, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created.id,
                project_id,
                created.source,
                created.target,
                created.relation,
                created.valid_from,
                created.valid_to,
                created.confidence,
                created.source_ref,
                created.status,
            ),
        )
        return created

    def list_relations(self, project_id: str) -> list[NarrativeRelation]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, source, target, relation, valid_from, valid_to,
                   confidence, source_ref, status
            FROM narrative_relations
            WHERE project_id = ?
            ORDER BY valid_from, source, relation, target, id
            """,
            (project_id,),
        ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def relations_at(self, project_id: str, scene_position: int) -> list[NarrativeRelation]:
        rows = self.connection.execute(
            """
            SELECT id, project_id, source, target, relation, valid_from, valid_to,
                   confidence, source_ref, status
            FROM narrative_relations
            WHERE project_id = ?
              AND status = 'confirmed'
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to >= ?)
            ORDER BY source, relation, target, valid_from DESC, id
            """,
            (project_id, scene_position, scene_position),
        ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def create_thread(self, project_id: str, thread: StoryThreadCreate) -> StoryThread:
        if (
            thread.target_payoff_from is not None
            and thread.target_payoff_to is not None
            and thread.target_payoff_to < thread.target_payoff_from
        ):
            raise ValueError("target_payoff_to cannot be before target_payoff_from")
        existing_ids = {
            row["id"] for row in self.connection.execute("SELECT id FROM story_threads")
        }
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
