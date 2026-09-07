"""Compatibility facade composed from focused application ports."""

from typing import Protocol

from app.data.ports.compiler import CompileDataPort
from app.data.ports.manuscript import ManuscriptDataPort
from app.data.ports.reference import ReferenceDataPort
from app.data.ports.snowflake import SnowflakeDataPort
from app.data.ports.writeback import WritebackDataPort
from app.models import (
    CanonEntity,
    CanonEntityCreate,
    CanonEntityUpdate,
    CharacterKnowledge,
    CharacterKnowledgeCreate,
    GenerationRun,
    KnowledgeState,
    KnowledgeStateAuthorCreate,
    KnowledgeStateCorrection,
    KnowledgeStateCreate,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    MemoryRecord,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    NarrativeRelation,
    NarrativeRelationCreate,
    NarrativeRevision,
    NarrativeVersionChange,
    ProjectCreate,
    ProjectSummary,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
    StoryFact,
    StoryFactCorrection,
    StoryFactCreate,
    StoryThread,
    StoryThreadCreate,
    StoryThreadEvent,
    StoryThreadEventCreate,
    StoryThreadStatusUpdate,
)
from app.outbox.models import OutboxJob, OutboxJobStatus
from app.domain_models.volume import (
    ManuscriptVolume,
    ManuscriptVolumeCreate,
    ChapterVolumeMembership,
)


class WritingDataStore(
    ManuscriptDataPort,
    SnowflakeDataPort,
    CompileDataPort,
    WritebackDataPort,
    ReferenceDataPort,
    Protocol,
):
    def create_manuscript_volume(
        self, project_id: str, create: ManuscriptVolumeCreate
    ) -> ManuscriptVolume: ...

    def update_manuscript_volume(
        self, project_id: str, volume_id: str, update: ManuscriptVolumeCreate
    ) -> ManuscriptVolume: ...

    def delete_manuscript_volume(self, project_id: str, volume_id: str) -> bool: ...

    def assign_chapter_volume(
        self, project_id: str, chapter_id: str, volume_id: str
    ) -> ChapterVolumeMembership: ...

    def get_scene_by_source(self, project_id: str, record_id: str) -> SceneContract | None:
        pass

    def init(self) -> None:
        pass

    def get_generation_run(self, project_id: str, run_id: str) -> GenerationRun | None:
        pass

    def list_generation_runs(self, project_id: str, limit: int = 100) -> list[GenerationRun]:
        pass

    def list_outbox_jobs(
        self,
        project_id: str,
        job_status: OutboxJobStatus | None = None,
        limit: int = 100,
        aggregate_type: str | None = None,
    ) -> list[OutboxJob]:
        pass

    def list_projects(self) -> list[ProjectSummary]:
        pass

    def create_project(self, project: ProjectCreate) -> ProjectSummary:
        pass

    def project_exists(self, project_id: str) -> bool:
        pass

    def advance_project_current_step(
        self, project_id: str, completed_step: int
    ) -> ProjectSummary | None:
        pass

    def create_canon_entity(self, project_id: str, entity: CanonEntityCreate) -> CanonEntity:
        pass

    def update_canon_entity(
        self, project_id: str, entity_id: str, entity: CanonEntityUpdate
    ) -> CanonEntity | None:
        pass

    def delete_canon_entity(self, project_id: str, entity_id: str) -> bool:
        pass

    def correct_story_fact(
        self, project_id: str, fact_id: str, change: StoryFactCorrection
    ) -> StoryFact: ...

    def retract_story_fact(
        self, project_id: str, fact_id: str, change: NarrativeVersionChange
    ) -> StoryFact: ...

    def create_author_knowledge(
        self, project_id: str, fact_id: str, create: KnowledgeStateAuthorCreate
    ) -> KnowledgeState: ...

    def correct_knowledge_state(
        self, project_id: str, fact_id: str, knowledge_id: str, change: KnowledgeStateCorrection
    ) -> KnowledgeState: ...

    def retract_knowledge_state(
        self, project_id: str, fact_id: str, knowledge_id: str, change: NarrativeVersionChange
    ) -> KnowledgeState: ...

    def list_narrative_history(self, project_id: str, fact_id: str) -> list[NarrativeRevision]: ...

    def get_story_fact(self, project_id: str, fact_id: str) -> StoryFact | None: ...

    def create_story_fact(self, project_id: str, fact: StoryFactCreate) -> StoryFact:
        pass

    def set_knowledge_state(
        self, project_id: str, fact_id: str, knowledge: KnowledgeStateCreate
    ) -> KnowledgeState:
        pass

    def list_knowledge_states(self, project_id: str, fact_id: str) -> list[KnowledgeState]:
        pass

    def set_character_knowledge(
        self, project_id: str, fact_id: str, knowledge: CharacterKnowledgeCreate
    ) -> CharacterKnowledge:
        pass

    def create_narrative_relation(
        self, project_id: str, relation: NarrativeRelationCreate
    ) -> NarrativeRelation:
        pass

    def list_narrative_relations_at(
        self, project_id: str, scene_position: int
    ) -> list[NarrativeRelation]:
        pass

    def create_story_thread(self, project_id: str, thread: StoryThreadCreate) -> StoryThread:
        pass

    def update_story_thread_status(
        self, project_id: str, thread_id: str, update: StoryThreadStatusUpdate
    ) -> StoryThread | None:
        pass

    def add_story_thread_event(
        self, project_id: str, thread_id: str, event: StoryThreadEventCreate
    ) -> StoryThreadEvent:
        pass

    def create_scene_contract(self, project_id: str, scene: SceneContractCreate) -> SceneContract:
        pass

    def update_scene_contract(
        self, project_id: str, scene_id: str, scene: SceneContractUpdate
    ) -> SceneContract | None:
        pass

    def delete_scene_contract(self, project_id: str, scene_id: str) -> bool:
        pass

    def create_manuscript_chapter(
        self, project_id: str, chapter: ManuscriptChapterCreate
    ) -> ManuscriptChapter:
        pass

    def update_manuscript_chapter(
        self, project_id: str, chapter_id: str, chapter: ManuscriptChapterUpdate
    ) -> ManuscriptChapter | None:
        pass

    def delete_manuscript_chapter(self, project_id: str, chapter_id: str) -> bool:
        pass

    def create_memory_record(self, project_id: str, record: MemoryRecordCreate) -> MemoryRecord:
        pass

    def update_memory_record(
        self, project_id: str, record_id: str, record: MemoryRecordUpdate
    ) -> MemoryRecord | None:
        pass

    def delete_memory_record(self, project_id: str, record_id: str) -> bool:
        pass
