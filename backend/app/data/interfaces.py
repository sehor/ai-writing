from typing import Protocol

from app.models import (
    CanonEntity,
    CanonEntityCreate,
    CanonEntityUpdate,
    CharacterKnowledge,
    CharacterKnowledgeCreate,
    GenerationAttempt,
    GenerationAttemptCreate,
    GenerationRun,
    GenerationRunCreate,
    GenerationRunUpdate,
    KnowledgeState,
    KnowledgeStateCreate,
    MemoryRecord,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalAcceptance,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    ProjectCreate,
    ProjectSummary,
    ReferenceSuggestion,
    ReferenceSuggestionCreate,
    ReferenceSuggestionStatus,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
    SceneProposal,
    SceneProposalCreate,
    SceneProposalStatus,
    SnowflakeArtifact,
    SnowflakeArtifactHead,
    SnowflakeArtifactRevision,
    SnowflakeArtifactRevisionCreate,
    SnowflakeRecordDecisionResponse,
    SnowflakeRecordRevision,
    SnowflakeRecordRevisionCreate,
    NarrativeRelation,
    NarrativeRelationCreate,
    StoryFact,
    StoryFactCreate,
    StoryThread,
    StoryThreadCreate,
    StoryThreadEvent,
    StoryThreadEventCreate,
    StoryThreadStatusUpdate,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)
from app.outbox.models import OutboxJob, OutboxJobStatus


class WritingDataStore(Protocol):
    def init(self) -> None:
        pass

    def create_generation_run(self, create: GenerationRunCreate) -> GenerationRun:
        pass

    def add_generation_attempt(
        self, run_id: str, create: GenerationAttemptCreate
    ) -> GenerationAttempt:
        pass

    def finish_generation_run(self, run_id: str, update: GenerationRunUpdate) -> None:
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

    def get_project(self, project_id: str) -> ProjectSummary | None:
        pass

    def project_exists(self, project_id: str) -> bool:
        pass

    def advance_project_current_step(
        self, project_id: str, completed_step: int
    ) -> ProjectSummary | None:
        pass

    def list_snowflake_artifacts(self, project_id: str) -> list[SnowflakeArtifact]:
        pass

    def get_snowflake_artifact(self, project_id: str, step_number: int) -> SnowflakeArtifact | None:
        pass

    def list_snowflake_revisions(
        self,
        project_id: str,
        step_number: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SnowflakeArtifactRevision], int]:
        pass

    def get_snowflake_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeArtifactRevision | None:
        pass

    def create_snowflake_revision(
        self,
        project_id: str,
        create: SnowflakeArtifactRevisionCreate,
        *,
        status: str | None = None,
        source: str | None = None,
    ) -> SnowflakeArtifactRevision:
        pass

    def patch_snowflake_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        content: str | None,
        structured_payload: dict | None,
    ) -> SnowflakeArtifactRevision | None:
        pass

    def list_snowflake_heads(self, project_id: str) -> list[SnowflakeArtifactHead]:
        pass

    def snowflake_pending_counts(self, project_id: str) -> dict[int, int]:
        pass

    def decide_snowflake_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        decision: str,
        expected_head_revision_id: str,
        review_reason: str = "",
    ) -> tuple[SnowflakeArtifactRevision, SnowflakeArtifactHead, list[int], str]:
        pass

    def skip_snowflake_step(
        self, project_id: str, step_number: int
    ) -> SnowflakeArtifactHead:
        pass

    def list_snowflake_records(
        self, project_id: str, step_number: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[SnowflakeRecordRevision], int]:
        pass

    def get_snowflake_records(
        self, project_id: str, step_number: int, record_ids: list[str]
    ) -> list[SnowflakeRecordRevision]:
        pass

    def list_accepted_snowflake_records(
        self, project_id: str, step_number: int
    ) -> list[SnowflakeRecordRevision]:
        pass

    def get_snowflake_record_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeRecordRevision | None:
        pass

    def create_snowflake_record_revision(
        self,
        project_id: str,
        create: SnowflakeRecordRevisionCreate,
        *,
        status: str = "draft",
    ) -> SnowflakeRecordRevision:
        pass

    def create_snowflake_record_revisions(
        self,
        project_id: str,
        creates: list[SnowflakeRecordRevisionCreate],
        *,
        status: str = "draft",
    ) -> list[SnowflakeRecordRevision]:
        pass

    def list_snowflake_record_revisions(
        self,
        project_id: str,
        step_number: int,
        record_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SnowflakeRecordRevision], int]:
        pass

    def decide_snowflake_record_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        decision: str,
        expected_revision_id: str,
        review_reason: str = "",
    ) -> SnowflakeRecordDecisionResponse:
        pass

    def list_canon_entities(self, project_id: str) -> list[CanonEntity]:
        pass

    def get_canon_entity(
        self,
        project_id: str,
        entity_id: str,
        connection: object | None = None,
    ) -> CanonEntity | None:
        pass

    def create_canon_entity(self, project_id: str, entity: CanonEntityCreate) -> CanonEntity:
        pass

    def update_canon_entity(
        self, project_id: str, entity_id: str, entity: CanonEntityUpdate
    ) -> CanonEntity | None:
        pass

    def delete_canon_entity(self, project_id: str, entity_id: str) -> bool:
        pass

    def create_story_fact(self, project_id: str, fact: StoryFactCreate) -> StoryFact:
        pass

    def list_story_facts(self, project_id: str) -> list[StoryFact]:
        pass

    def list_story_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
        pass

    def list_reader_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
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

    def list_character_facts_at(
        self, project_id: str, character: str, scene_position: int
    ) -> list[StoryFact]:
        pass

    def create_narrative_relation(
        self, project_id: str, relation: NarrativeRelationCreate
    ) -> NarrativeRelation:
        pass

    def list_narrative_relations(self, project_id: str) -> list[NarrativeRelation]:
        pass

    def list_narrative_relations_at(
        self, project_id: str, scene_position: int
    ) -> list[NarrativeRelation]:
        pass

    def create_story_thread(self, project_id: str, thread: StoryThreadCreate) -> StoryThread:
        pass

    def list_story_threads(self, project_id: str) -> list[StoryThread]:
        pass

    def update_story_thread_status(
        self, project_id: str, thread_id: str, update: StoryThreadStatusUpdate
    ) -> StoryThread | None:
        pass

    def add_story_thread_event(
        self, project_id: str, thread_id: str, event: StoryThreadEventCreate
    ) -> StoryThreadEvent:
        pass

    def list_story_thread_events(self, project_id: str, thread_id: str) -> list[StoryThreadEvent]:
        pass

    def list_scene_contracts(self, project_id: str) -> list[SceneContract]:
        pass

    def get_scene_contract(self, project_id: str, scene_id: str) -> SceneContract | None:
        pass

    def create_scene_contract(self, project_id: str, scene: SceneContractCreate) -> SceneContract:
        pass

    def update_scene_contract(
        self, project_id: str, scene_id: str, scene: SceneContractUpdate
    ) -> SceneContract | None:
        pass

    def delete_scene_contract(self, project_id: str, scene_id: str) -> bool:
        pass

    def list_manuscript_chapters(self, project_id: str) -> list[ManuscriptChapter]:
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

    def list_memory_records(self, project_id: str) -> list[MemoryRecord]:
        pass

    def create_memory_record(self, project_id: str, record: MemoryRecordCreate) -> MemoryRecord:
        pass

    def update_memory_record(
        self, project_id: str, record_id: str, record: MemoryRecordUpdate
    ) -> MemoryRecord | None:
        pass

    def delete_memory_record(self, project_id: str, record_id: str) -> bool:
        pass

    def list_manuscript_proposals(self, project_id: str) -> list[ManuscriptProposal]:
        pass

    def create_manuscript_proposal(
        self, project_id: str, proposal: ManuscriptProposalCreate
    ) -> ManuscriptProposal:
        pass

    def update_manuscript_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: ManuscriptProposalStatus,
    ) -> ManuscriptProposal | None:
        pass

    def get_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptProposal | None:
        pass

    def list_manuscript_scenes(self, project_id: str) -> list[ManuscriptScene]:
        pass

    def list_manuscript_revisions(self, project_id: str) -> list[ManuscriptRevision]:
        pass

    def get_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptRevision | None:
        pass

    def accept_manuscript_proposal(
        self, project_id: str, proposal_id: str, draft: ManuscriptProposalAcceptance | None = None
    ) -> ManuscriptScene | None:
        pass

    def restore_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptScene | None:
        pass

    def update_manuscript_scene(
        self, project_id: str, scene_id: str, update: ManuscriptSceneUpdate
    ) -> ManuscriptScene | None:
        pass

    def list_writeback_proposals(self, project_id: str) -> list[WritebackProposal]:
        pass

    def create_writeback_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal:
        pass

    def create_writeback_proposals(
        self, project_id: str, proposals: list[WritebackProposalCreate]
    ) -> list[WritebackProposal]:
        pass

    def update_writeback_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: WritebackProposalStatus,
    ) -> WritebackProposal | None:
        pass

    def get_writeback_proposal(
        self,
        project_id: str,
        proposal_id: str,
        connection: object | None = None,
    ) -> WritebackProposal | None:
        pass

    def get_analysis_run(
        self,
        project_id: str,
        source_ref: str,
        processor: str,
        input_hash: str | None = None,
    ) -> object | None:
        pass

    def list_reference_suggestions(self, project_id: str) -> list[ReferenceSuggestion]:
        pass

    def create_reference_suggestion(
        self, project_id: str, suggestion: ReferenceSuggestionCreate
    ) -> ReferenceSuggestion:
        pass

    def update_reference_suggestion_status(
        self,
        project_id: str,
        suggestion_id: str,
        suggestion_status: ReferenceSuggestionStatus,
    ) -> ReferenceSuggestion | None:
        pass

    def list_scene_proposals(
        self, project_id: str, status: str | None = None
    ) -> list[SceneProposal]:
        pass

    def get_scene_proposal(
        self,
        project_id: str,
        proposal_id: str,
        connection: object | None = None,
    ) -> SceneProposal | None:
        pass

    def create_scene_proposals(
        self,
        project_id: str,
        proposals: list[SceneProposalCreate],
        connection: object | None = None,
    ) -> list[SceneProposal]:
        pass

    def update_scene_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: SceneProposalStatus,
    ) -> SceneProposal | None:
        pass

    def accept_scene_proposals(
        self, project_id: str, proposal_ids: list[str]
    ) -> tuple[list[SceneContract], list[SceneProposal]]:
        pass
