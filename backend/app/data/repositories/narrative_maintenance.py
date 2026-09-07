"""Audited author corrections inside the caller's narrative transaction."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING
from uuid import uuid4

from app.data.helpers import utc_now
from app.errors import InvalidOperationError, ResourceNotFoundError, StateConflictError
from app.models import (
    KnowledgeState,
    KnowledgeStateAuthorCreate,
    KnowledgeStateCorrection,
    KnowledgeStateCreate,
    NarrativeRevision,
    NarrativeVersionChange,
    StoryFact,
    StoryFactCorrection,
    StoryFactCreate,
)

if TYPE_CHECKING:
    from app.data.repositories.narrative import NarrativeRepository


def narrative_revision_from_row(row: sqlite3.Row) -> NarrativeRevision:
    return NarrativeRevision(
        id=row["id"],
        project_id=row["project_id"],
        fact_id=row["fact_id"],
        knowledge_state_id=row["knowledge_state_id"] or "",
        version=row["version"],
        reason=row["reason"],
        created_at=row["created_at"],
        record=json.loads(row["record_json"]),
    )


def record_revision(
    connection: sqlite3.Connection, record: StoryFact | KnowledgeState, reason: str
):
    fact_id = record.fact_id if isinstance(record, KnowledgeState) else record.id
    knowledge_id = record.id if isinstance(record, KnowledgeState) else None
    # Legacy rows receive their original baseline before their first change.
    if connection.execute(
        "SELECT 1 FROM narrative_revisions WHERE project_id=? AND fact_id=? "
        "AND knowledge_state_id IS ? AND version=?",
        (record.project_id, fact_id, knowledge_id, record.version),
    ).fetchone():
        return
    connection.execute(
        "INSERT INTO narrative_revisions "
        "(id, project_id, fact_id, knowledge_state_id, version, reason, created_at, record_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"narrative-revision-{uuid4().hex}",
            record.project_id,
            fact_id,
            knowledge_id,
            record.version,
            reason,
            utc_now(),
            record.model_dump_json(),
        ),
    )


def validate_fact(fact: StoryFactCreate):
    if not all(value.strip() for value in (fact.subject, fact.predicate, fact.value)):
        raise ValueError("Fact subject, predicate and value cannot be blank")
    if fact.valid_to_scene is not None and fact.valid_to_scene < fact.valid_from_scene:
        raise ValueError("valid_to_scene cannot be before valid_from_scene")
    if fact.reader_visible_from is not None:
        validate_position(fact, fact.reader_visible_from)


def validate_position(fact: StoryFactCreate, position: int):
    if position < fact.valid_from_scene or (
        fact.valid_to_scene is not None and position > fact.valid_to_scene
    ):
        raise ValueError("Knowledge position must be within the fact's validity interval")


def validate_knowledge(fact: StoryFact, knowledge: KnowledgeStateCreate):
    if knowledge.status != "retracted":
        validate_position(fact, knowledge.known_from_scene)
    if knowledge.status == "confirmed" and fact.status != "confirmed":
        raise ValueError("Knowledge cannot be confirmed until its fact is confirmed")
    if knowledge.scope == "world_truth" and (
        knowledge.known_from_scene != fact.valid_from_scene or knowledge.status != fact.status
    ):
        raise ValueError("World truth knowledge is derived from the fact")


class NarrativeMaintenance:
    def __init__(self, repository: NarrativeRepository):
        self.repository = repository
        self.connection = repository.connection

    def require_fact(self, project_id: str, fact_id: str) -> StoryFact:
        fact = self.repository.get_fact(project_id, fact_id)
        if fact is None:
            raise ResourceNotFoundError("Story fact not found")
        return fact

    def require_knowledge(self, project_id: str, fact_id: str, knowledge_id: str) -> KnowledgeState:
        self.require_fact(project_id, fact_id)
        state = self.repository.get_knowledge(project_id, fact_id, knowledge_id)
        if state is None:
            raise ResourceNotFoundError("Knowledge state not found")
        return state

    @staticmethod
    def check_version(record: StoryFact | KnowledgeState, expected: int):
        if record.version != expected:
            raise StateConflictError("Narrative record changed; reload before correcting it")

    def correct_fact(self, project_id: str, fact_id: str, change: StoryFactCorrection) -> StoryFact:
        current = self.require_fact(project_id, fact_id)
        self.check_version(current, change.expected_version)
        if change.status != "retracted":
            validate_fact(change)
        record_revision(self.connection, current, "Original baseline")
        updated = StoryFact(
            id=current.id,
            project_id=project_id,
            version=current.version + 1,
            updated_at=utc_now(),
            **change.model_dump(exclude={"reason", "expected_version"}),
        )
        columns = list(StoryFactCreate.model_fields) + ["version", "updated_at"]
        self.connection.execute(
            "UPDATE story_facts SET "
            + ", ".join(f"{column}=?" for column in columns)
            + " WHERE project_id=? AND id=?",
            [getattr(updated, column) for column in columns] + [project_id, fact_id],
        )
        for state in self.repository.list_knowledge_states(project_id, fact_id):
            if state.scope == "world_truth":
                continue
            if state.scope == "reader_knowledge" and updated.reader_visible_from is not None:
                continue
            # Do not transfer knowledge of old content to the corrected fact.
            status = "retracted" if updated.status == "retracted" else "planned"
            self.repository.write_knowledge(
                state.model_copy(
                    update={"status": status, "version": state.version + 1, "updated_at": utc_now()}
                ),
                change.reason,
                previous=state,
                sync_reader=False,
            )
        self.repository.set_knowledge_state(
            project_id,
            fact_id,
            KnowledgeStateCreate(
                scope="world_truth",
                known_from_scene=updated.valid_from_scene,
                source_ref=updated.source_ref,
                status=updated.status,
            ),
            reason=change.reason,
            sync_reader=False,
        )
        if updated.reader_visible_from is not None:
            self.repository.set_knowledge_state(
                project_id,
                fact_id,
                KnowledgeStateCreate(
                    scope="reader_knowledge",
                    known_from_scene=updated.reader_visible_from,
                    source_ref=updated.source_ref,
                    status=updated.status,
                ),
                reason=change.reason,
                sync_reader=False,
            )
        record_revision(self.connection, updated, change.reason)
        return updated

    def retract_fact(
        self, project_id: str, fact_id: str, change: NarrativeVersionChange
    ) -> StoryFact:
        current = self.require_fact(project_id, fact_id)
        return self.correct_fact(
            project_id,
            fact_id,
            StoryFactCorrection(
                **current.model_dump(
                    exclude={"id", "project_id", "version", "updated_at", "status"}
                ),
                **change.model_dump(),
                status="retracted",
            ),
        )

    def create_knowledge(self, project_id: str, fact_id: str, create: KnowledgeStateAuthorCreate):
        self.require_fact(project_id, fact_id)
        if create.scope == "world_truth":
            raise InvalidOperationError("World truth knowledge is derived from the fact")
        if self.connection.execute(
            "SELECT 1 FROM knowledge_states WHERE project_id=? AND fact_id=? AND scope=? AND character=?",
            (project_id, fact_id, create.scope, create.character),
        ).fetchone():
            raise StateConflictError(
                "Knowledge state already exists; use its version to correct it"
            )
        return self.repository.set_knowledge_state(
            project_id,
            fact_id,
            KnowledgeStateCreate(**create.model_dump(exclude={"reason"})),
            reason=create.reason,
        )

    def correct_knowledge(
        self, project_id: str, fact_id: str, knowledge_id: str, change: KnowledgeStateCorrection
    ):
        current = self.require_knowledge(project_id, fact_id, knowledge_id)
        self.check_version(current, change.expected_version)
        if current.scope == "world_truth":
            raise InvalidOperationError("World truth knowledge is derived from the fact")
        if (change.scope, change.character.casefold()) != (
            current.scope,
            current.character.casefold(),
        ):
            raise InvalidOperationError("Knowledge scope and character identity cannot be changed")
        return self.repository.set_knowledge_state(
            project_id,
            fact_id,
            KnowledgeStateCreate(**change.model_dump(exclude={"reason", "expected_version"})),
            reason=change.reason,
        )

    def retract_knowledge(
        self, project_id: str, fact_id: str, knowledge_id: str, change: NarrativeVersionChange
    ):
        current = self.require_knowledge(project_id, fact_id, knowledge_id)
        return self.correct_knowledge(
            project_id,
            fact_id,
            knowledge_id,
            KnowledgeStateCorrection(
                **current.model_dump(
                    exclude={"id", "project_id", "fact_id", "version", "updated_at", "status"}
                ),
                **change.model_dump(),
                status="retracted",
            ),
        )

    def history(self, project_id: str, fact_id: str) -> list[NarrativeRevision]:
        self.require_fact(project_id, fact_id)
        rows = self.connection.execute(
            "SELECT * FROM narrative_revisions WHERE project_id=? AND fact_id=? "
            "ORDER BY created_at, version, id",
            (project_id, fact_id),
        ).fetchall()
        return [narrative_revision_from_row(row) for row in rows]
