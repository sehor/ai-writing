from __future__ import annotations

import sqlite3
from typing import Protocol

from app.models import (
    CanonEntity,
    ManuscriptScene,
    MemoryRecord,
    NarrativeRelation,
    ProjectSummary,
    SceneContract,
    SnowflakeArtifact,
    StoryFact,
    StoryThread,
    StoryThreadEvent,
)


class ContextReader(Protocol):
    def get_project(self, project_id: str) -> ProjectSummary | None: ...

    def list_canon_entities(self, project_id: str) -> list[CanonEntity]: ...

    def list_manuscript_scenes(self, project_id: str) -> list[ManuscriptScene]: ...

    def list_memory_records(self, project_id: str) -> list[MemoryRecord]: ...

    def list_scene_contracts(self, project_id: str) -> list[SceneContract]: ...

    def list_story_thread_events(
        self, project_id: str, thread_id: str
    ) -> list[StoryThreadEvent]: ...

    def list_story_threads(self, project_id: str) -> list[StoryThread]: ...


class ProjectSnapshotReader(ContextReader, Protocol):
    def list_snowflake_artifacts(self, project_id: str) -> list[SnowflakeArtifact]: ...


class NarrativeGraphReader(Protocol):
    def list_narrative_relations(self, project_id: str) -> list[NarrativeRelation]: ...


class NarrativeSnapshotReader(ContextReader, NarrativeGraphReader, Protocol):
    def get_scene_contract(
        self, project_id: str, scene_id: str, connection: sqlite3.Connection | None = None
    ) -> SceneContract | None: ...

    def list_character_facts_at(
        self, project_id: str, character: str, scene_position: int
    ) -> list[StoryFact]: ...

    def list_reader_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]: ...

    def list_story_facts(self, project_id: str) -> list[StoryFact]: ...

    def list_story_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]: ...


class ReviewTargetReader(Protocol):
    def get_canon_entity(
        self, project_id: str, entity_id: str, connection: sqlite3.Connection | None = None
    ) -> CanonEntity | None: ...

    def list_canon_entities(self, project_id: str) -> list[CanonEntity]: ...

    def list_story_threads(self, project_id: str) -> list[StoryThread]: ...
