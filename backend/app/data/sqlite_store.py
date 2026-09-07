"""SQLiteWritingDataStore: the public facade of the persistence layer.

Since P2-03 the SQL lives in per-aggregate repositories
(app.data.repositories); this class only coordinates them. Every public
method name and signature is unchanged from the mixin-based store:

- Single-aggregate operations open a short SqliteUnitOfWork internally.
- Multi-step transactional flows (acceptance, restore, batch accept,
  write-back apply, outbox enqueueing) run inside ONE unit of work and
  delegate to app.data.transactions.
- Methods that historically accepted a trailing (or leading) connection
  argument still do; the connection-scoped repository is constructed on
  the spot so callers can keep composing transactions via connect().
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.data.migrations import initialize_schema
from app.data.repositories.analysis import AnalysisRepository
from app.data.repositories.canon import CanonRepository
from app.data.repositories.memory import MemoryRepository
from app.data.repositories.narrative_maintenance import NarrativeMaintenance
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.projects import ProjectRepository
from app.data.repositories.review import ReviewRepository
from app.data.repositories.scene_proposals import SceneProposalRepository
from app.data.repositories.scenes import SceneRepository
from app.data.repositories.snowflake_records import SnowflakeRecordRepository
from app.data.transactions.manuscript import (
    accept_manuscript_proposal,
    restore_manuscript_revision,
    update_manuscript_scene,
)
from app.data.transactions.revision_jobs import (
    enqueue_manuscript_revision_analysis_jobs,
    enqueue_manuscript_revision_index_job,
)
from app.data.transactions.scene_compile import accept_scene_proposals
from app.data.transactions.snowflake import (
    decide_snowflake_record_revision,
    decide_snowflake_revision,
)
from app.data.transactions.writeback import accept_writeback_proposal
from app.data.unit_of_work import SqliteUnitOfWork, open_connection
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
    KnowledgeStateAuthorCreate,
    KnowledgeStateCorrection,
    KnowledgeStateCreate,
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
    MemoryRecord,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    NarrativeRelation,
    NarrativeRelationCreate,
    NarrativeRevision,
    NarrativeVersionChange,
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
    StoryFact,
    StoryFactCorrection,
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
from app.outbox.models import AnalysisExecution, OutboxJob, OutboxJobStatus


class SQLiteWritingDataStore:
    """Facade over the repositories; owns the database path only."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    # ------------------------------------------------------------------
    # Lifecycle / connections
    # ------------------------------------------------------------------

    def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = open_connection(self.database_path)
        try:
            with connection:
                initialize_schema(connection)
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Generation runs
    # ------------------------------------------------------------------

    def create_generation_run(self, create: GenerationRunCreate) -> GenerationRun:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.generation_runs.create(create)

    def add_generation_attempt(
        self, run_id: str, create: GenerationAttemptCreate
    ) -> GenerationAttempt:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.generation_runs.add_attempt(run_id, create)

    def finish_generation_run(self, run_id: str, update: GenerationRunUpdate) -> None:
        with SqliteUnitOfWork(self.database_path) as uow:
            uow.generation_runs.finish(run_id, update)

    def get_generation_run(self, project_id: str, run_id: str) -> GenerationRun | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.generation_runs.get(project_id, run_id)

    def list_generation_runs(self, project_id: str, limit: int = 100) -> list[GenerationRun]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.generation_runs.list(project_id, limit)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = open_connection(self.database_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def list_projects(self) -> list[ProjectSummary]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.projects.list()

    def create_project(self, project: ProjectCreate) -> ProjectSummary:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.projects.create(project)

    def get_project(self, project_id: str) -> ProjectSummary | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.projects.get(project_id)

    def project_exists(self, project_id: str) -> bool:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.projects.exists(project_id)

    def advance_project_current_step(
        self,
        project_id: str,
        completed_step: int,
        connection: sqlite3.Connection | None = None,
    ) -> ProjectSummary | None:
        if connection is not None:
            return ProjectRepository(connection).advance_current_step(project_id, completed_step)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.projects.advance_current_step(project_id, completed_step)

    # ------------------------------------------------------------------
    # Snowflake artifacts
    # ------------------------------------------------------------------

    def list_snowflake_artifacts(self, project_id: str) -> list[SnowflakeArtifact]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.list_by_project(project_id)

    def get_snowflake_artifact(self, project_id: str, step_number: int) -> SnowflakeArtifact | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.get(project_id, step_number)

    def list_snowflake_revisions(
        self,
        project_id: str,
        step_number: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SnowflakeArtifactRevision], int]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.list_revisions(project_id, step_number, limit=limit, offset=offset)

    def get_snowflake_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeArtifactRevision | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.get_revision(project_id, revision_id)

    def create_snowflake_revision(
        self,
        project_id: str,
        create: SnowflakeArtifactRevisionCreate,
        *,
        status: str | None = None,
        source: str | None = None,
    ) -> SnowflakeArtifactRevision:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.create_revision(project_id, create, status=status, source=source)

    def patch_snowflake_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        content: str | None,
        structured_payload: dict | None,
    ) -> SnowflakeArtifactRevision | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.patch_revision(
                project_id,
                revision_id,
                content=content,
                structured_payload=structured_payload,
            )

    def list_snowflake_heads(self, project_id: str) -> list[SnowflakeArtifactHead]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.snowflake.list_heads(project_id)

    def snowflake_pending_counts(self, project_id: str) -> dict[int, int]:
        with SqliteUnitOfWork(self.database_path) as uow:
            counts = uow.snowflake.pending_counts(project_id)
            record_counts = SnowflakeRecordRepository(uow.connection).pending_counts(project_id)
            for step_number in (6, 7, 8, 9):
                counts[step_number] = record_counts.get(step_number, 0)
            return counts

    def decide_snowflake_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        decision: str,
        expected_head_revision_id: str,
        review_reason: str = "",
    ) -> tuple[SnowflakeArtifactRevision, SnowflakeArtifactHead, list[int], str]:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            # Reserve the writer before reading the head used by optimistic checks.
            return decide_snowflake_revision(
                uow.connection,
                project_id=project_id,
                revision_id=revision_id,
                decision=decision,
                expected_head_revision_id=expected_head_revision_id,
                review_reason=review_reason,
            )

    def skip_snowflake_step(self, project_id: str, step_number: int) -> SnowflakeArtifactHead:
        with SqliteUnitOfWork(self.database_path) as uow:
            head = uow.snowflake.skip_step(project_id, step_number)
            uow.projects.advance_current_step(project_id, step_number)
            return head

    def list_snowflake_records(
        self, project_id: str, step_number: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[SnowflakeRecordRevision], int]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return SnowflakeRecordRepository(uow.connection).list_current(
                project_id, step_number, limit=limit, offset=offset
            )

    def get_snowflake_records(
        self, project_id: str, step_number: int, record_ids: list[str]
    ) -> list[SnowflakeRecordRevision]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return SnowflakeRecordRepository(uow.connection).get_accepted_by_record_ids(
                project_id, step_number, record_ids
            )

    def list_accepted_snowflake_records(
        self, project_id: str, step_number: int
    ) -> list[SnowflakeRecordRevision]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return SnowflakeRecordRepository(uow.connection).list_accepted(project_id, step_number)

    def get_snowflake_record_revision(
        self, project_id: str, revision_id: str
    ) -> SnowflakeRecordRevision | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return SnowflakeRecordRepository(uow.connection).get_revision(project_id, revision_id)

    def create_snowflake_record_revision(
        self,
        project_id: str,
        create: SnowflakeRecordRevisionCreate,
        *,
        status: str = "draft",
    ) -> SnowflakeRecordRevision:
        with SqliteUnitOfWork(self.database_path) as uow:
            return SnowflakeRecordRepository(uow.connection).create(
                project_id, create, status=status
            )

    def create_snowflake_record_revisions(
        self,
        project_id: str,
        creates: list[SnowflakeRecordRevisionCreate],
        *,
        status: str = "draft",
    ) -> list[SnowflakeRecordRevision]:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            repository = SnowflakeRecordRepository(uow.connection)
            return [repository.create(project_id, create, status=status) for create in creates]

    def list_snowflake_record_revisions(
        self,
        project_id: str,
        step_number: int,
        record_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SnowflakeRecordRevision], int]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return SnowflakeRecordRepository(uow.connection).list_history(
                project_id, step_number, record_id, limit=limit, offset=offset
            )

    def decide_snowflake_record_revision(
        self,
        project_id: str,
        revision_id: str,
        *,
        decision: str,
        expected_revision_id: str,
        review_reason: str = "",
    ) -> SnowflakeRecordDecisionResponse:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return decide_snowflake_record_revision(
                uow.connection,
                project_id=project_id,
                revision_id=revision_id,
                decision=decision,
                expected_revision_id=expected_revision_id,
                review_reason=review_reason,
            )

    # ------------------------------------------------------------------
    # Canon entities
    # ------------------------------------------------------------------

    def list_canon_entities(self, project_id: str) -> list[CanonEntity]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.canon.list(project_id)

    def get_canon_entity(
        self,
        project_id: str,
        entity_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> CanonEntity | None:
        if connection is not None:
            return CanonRepository(connection).get(project_id, entity_id)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.canon.get(project_id, entity_id)

    def create_canon_entity(
        self,
        project_id: str,
        entity: CanonEntityCreate,
        connection: sqlite3.Connection | None = None,
    ) -> CanonEntity:
        if connection is not None:
            return CanonRepository(connection).create(project_id, entity)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.canon.create(project_id, entity)

    def update_canon_entity(
        self, project_id: str, entity_id: str, entity: CanonEntityUpdate
    ) -> CanonEntity | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.canon.update(project_id, entity_id, entity)

    def delete_canon_entity(self, project_id: str, entity_id: str) -> bool:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.canon.delete(project_id, entity_id)

    # ------------------------------------------------------------------
    # Narrative state: temporal facts / knowledge / story threads
    # ------------------------------------------------------------------

    def correct_story_fact(
        self, project_id: str, fact_id: str, change: StoryFactCorrection
    ) -> StoryFact:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return NarrativeMaintenance(uow.narrative).correct_fact(project_id, fact_id, change)

    def retract_story_fact(
        self, project_id: str, fact_id: str, change: NarrativeVersionChange
    ) -> StoryFact:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return NarrativeMaintenance(uow.narrative).retract_fact(project_id, fact_id, change)

    def create_author_knowledge(
        self, project_id: str, fact_id: str, create: KnowledgeStateAuthorCreate
    ) -> KnowledgeState:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return NarrativeMaintenance(uow.narrative).create_knowledge(project_id, fact_id, create)

    def correct_knowledge_state(
        self, project_id: str, fact_id: str, knowledge_id: str, change: KnowledgeStateCorrection
    ) -> KnowledgeState:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return NarrativeMaintenance(uow.narrative).correct_knowledge(
                project_id, fact_id, knowledge_id, change
            )

    def retract_knowledge_state(
        self, project_id: str, fact_id: str, knowledge_id: str, change: NarrativeVersionChange
    ) -> KnowledgeState:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return NarrativeMaintenance(uow.narrative).retract_knowledge(
                project_id, fact_id, knowledge_id, change
            )

    def list_narrative_history(self, project_id: str, fact_id: str) -> list[NarrativeRevision]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return NarrativeMaintenance(uow.narrative).history(project_id, fact_id)

    def get_story_fact(self, project_id: str, fact_id: str) -> StoryFact | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.get_fact(project_id, fact_id)

    def create_story_fact(self, project_id: str, fact: StoryFactCreate) -> StoryFact:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return uow.narrative.create_fact(project_id, fact)

    def list_story_facts(self, project_id: str) -> list[StoryFact]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.list_facts(project_id)

    def list_story_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.facts_at(project_id, scene_position)

    def list_reader_facts_at(self, project_id: str, scene_position: int) -> list[StoryFact]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.reader_facts_at(project_id, scene_position)

    def set_knowledge_state(
        self,
        project_id: str,
        fact_id: str,
        knowledge: KnowledgeStateCreate,
    ) -> KnowledgeState:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return uow.narrative.set_knowledge_state(project_id, fact_id, knowledge)

    def list_knowledge_states(self, project_id: str, fact_id: str) -> list[KnowledgeState]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.list_knowledge_states(project_id, fact_id)

    def set_character_knowledge(
        self,
        project_id: str,
        fact_id: str,
        knowledge: CharacterKnowledgeCreate,
    ) -> CharacterKnowledge:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return uow.narrative.set_character_knowledge(project_id, fact_id, knowledge)

    def list_character_facts_at(
        self,
        project_id: str,
        character: str,
        scene_position: int,
    ) -> list[StoryFact]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.character_facts_at(project_id, character, scene_position)

    def create_narrative_relation(
        self,
        project_id: str,
        relation: NarrativeRelationCreate,
    ) -> NarrativeRelation:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.create_relation(project_id, relation)

    def list_narrative_relations(self, project_id: str) -> list[NarrativeRelation]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.list_relations(project_id)

    def list_narrative_relations_at(
        self,
        project_id: str,
        scene_position: int,
    ) -> list[NarrativeRelation]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.relations_at(project_id, scene_position)

    def create_story_thread(self, project_id: str, thread: StoryThreadCreate) -> StoryThread:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.create_thread(project_id, thread)

    def list_story_threads(self, project_id: str) -> list[StoryThread]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.list_threads(project_id)

    def update_story_thread_status(
        self,
        project_id: str,
        thread_id: str,
        update: StoryThreadStatusUpdate,
    ) -> StoryThread | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.set_thread_status(project_id, thread_id, update.status)

    def add_story_thread_event(
        self,
        project_id: str,
        thread_id: str,
        event: StoryThreadEventCreate,
    ) -> StoryThreadEvent:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.add_thread_event(project_id, thread_id, event)

    def list_story_thread_events(
        self,
        project_id: str,
        thread_id: str,
    ) -> list[StoryThreadEvent]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.narrative.list_thread_events(project_id, thread_id)

    # ------------------------------------------------------------------
    # Scene contracts
    # ------------------------------------------------------------------

    def list_scene_contracts(self, project_id: str) -> list[SceneContract]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scenes.list(project_id)

    def get_scene_by_source(self, project_id: str, record_id: str) -> SceneContract | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scenes.get_by_source(project_id, record_id)

    def get_scene_contract(
        self,
        project_id: str,
        scene_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> SceneContract | None:
        if connection is not None:
            return SceneRepository(connection).get(project_id, scene_id)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scenes.get(project_id, scene_id)

    def create_scene_contract(self, project_id: str, scene: SceneContractCreate) -> SceneContract:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scenes.insert(project_id, scene)

    def insert_scene_contract(
        self,
        project_id: str,
        scene: SceneContractCreate,
        connection: sqlite3.Connection,
    ) -> SceneContract:
        """Legacy helper kept for callers composing their own transaction."""
        return SceneRepository(connection).insert(project_id, scene)

    def update_scene_contract(
        self, project_id: str, scene_id: str, scene: SceneContractUpdate
    ) -> SceneContract | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scenes.update(project_id, scene_id, scene)

    def delete_scene_contract(self, project_id: str, scene_id: str) -> bool:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scenes.delete(project_id, scene_id)

    # ------------------------------------------------------------------
    # Parsed scene proposals (P1-05)
    # ------------------------------------------------------------------

    def list_scene_proposals(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[SceneProposal]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scene_proposals.list(project_id, status)

    def get_scene_proposal(
        self,
        project_id: str,
        proposal_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> SceneProposal | None:
        if connection is not None:
            return SceneProposalRepository(connection).get(project_id, proposal_id)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scene_proposals.get(project_id, proposal_id)

    def create_scene_proposals(
        self,
        project_id: str,
        proposals: list[SceneProposalCreate],
        connection: sqlite3.Connection | None = None,
    ) -> list[SceneProposal]:
        if connection is not None:
            return SceneProposalRepository(connection).create_batch(project_id, proposals)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scene_proposals.create_batch(project_id, proposals)

    def supersede_pending_scene_proposals(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
        except_ids: set[str] | None = None,
    ) -> int:
        return SceneProposalRepository(connection).supersede_pending(
            project_id=project_id,
            source_ref=source_ref,
            except_ids=except_ids,
        )

    def update_scene_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: SceneProposalStatus,
    ) -> SceneProposal | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.scene_proposals.update_status(project_id, proposal_id, proposal_status)

    def accept_scene_proposals(
        self, project_id: str, proposal_ids: list[str]
    ) -> tuple[list[SceneContract], list[SceneProposal]]:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return accept_scene_proposals(
                uow.connection, project_id=project_id, proposal_ids=proposal_ids
            )

    # ------------------------------------------------------------------
    # Manuscript chapters
    # ------------------------------------------------------------------

    def list_manuscript_chapters(self, project_id: str) -> list[ManuscriptChapter]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.list_chapters(project_id)

    def create_manuscript_chapter(
        self, project_id: str, chapter: ManuscriptChapterCreate
    ) -> ManuscriptChapter:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.create_chapter(project_id, chapter)

    def update_manuscript_chapter(
        self, project_id: str, chapter_id: str, chapter: ManuscriptChapterUpdate
    ) -> ManuscriptChapter | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.update_chapter(project_id, chapter_id, chapter)

    def delete_manuscript_chapter(self, project_id: str, chapter_id: str) -> bool:
        """Delete a chapter and detach its contracts inside one transaction."""
        with SqliteUnitOfWork(self.database_path) as uow:
            deleted = uow.manuscripts.delete_chapter(project_id, chapter_id)
            if deleted:
                uow.scenes.clear_chapter_reference(project_id, chapter_id)
        return deleted

    # ------------------------------------------------------------------
    # Manuscript proposals / scenes / revisions
    # ------------------------------------------------------------------

    def list_manuscript_proposals(self, project_id: str) -> list[ManuscriptProposal]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.list_proposals(project_id)

    def create_manuscript_proposal(
        self, project_id: str, proposal: ManuscriptProposalCreate
    ) -> ManuscriptProposal:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.create_proposal(project_id, proposal)

    def get_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptProposal | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.get_proposal(project_id, proposal_id)

    def update_manuscript_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: ManuscriptProposalStatus,
    ) -> ManuscriptProposal | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.update_proposal_status(project_id, proposal_id, proposal_status)

    def list_manuscript_scenes(self, project_id: str) -> list[ManuscriptScene]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.list_scenes(project_id)

    def get_manuscript_scene(self, project_id: str, scene_id: str) -> ManuscriptScene | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.get_scene(project_id, scene_id)

    def list_manuscript_revisions(self, project_id: str) -> list[ManuscriptRevision]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.list_revisions(project_id)

    def get_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptRevision | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.manuscripts.get_revision(project_id, revision_id)

    def accept_manuscript_proposal(
        self, project_id: str, proposal_id: str, draft: ManuscriptProposalAcceptance | None = None
    ) -> ManuscriptScene | None:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return accept_manuscript_proposal(
                uow.connection, project_id=project_id, proposal_id=proposal_id, draft=draft
            )

    def restore_manuscript_revision(
        self, project_id: str, revision_id: str
    ) -> ManuscriptScene | None:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return restore_manuscript_revision(
                uow.connection, project_id=project_id, revision_id=revision_id
            )

    def update_manuscript_scene(
        self, project_id: str, scene_id: str, update: ManuscriptSceneUpdate
    ) -> ManuscriptScene | None:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            # Serialize the version check and all revision/outbox writes.
            return update_manuscript_scene(
                uow.connection, project_id=project_id, scene_id=scene_id, update=update
            )

    # ------------------------------------------------------------------
    # Memory records
    # ------------------------------------------------------------------

    def list_memory_records(self, project_id: str) -> list[MemoryRecord]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.memory.list(project_id)

    def create_memory_record(
        self,
        project_id: str,
        record: MemoryRecordCreate,
        connection: sqlite3.Connection | None = None,
    ) -> MemoryRecord:
        if connection is not None:
            return MemoryRepository(connection).create(project_id, record)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.memory.create(project_id, record)

    def update_memory_record(
        self, project_id: str, record_id: str, record: MemoryRecordUpdate
    ) -> MemoryRecord | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.memory.update(project_id, record_id, record)

    def delete_memory_record(self, project_id: str, record_id: str) -> bool:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.memory.delete(project_id, record_id)

    # ------------------------------------------------------------------
    # Review records: write-back proposals and reference suggestions
    # ------------------------------------------------------------------

    def list_writeback_proposals(self, project_id: str) -> list[WritebackProposal]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.list_writebacks(project_id)

    def get_writeback_proposal(
        self,
        project_id: str,
        proposal_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> WritebackProposal | None:
        if connection is not None:
            return ReviewRepository(connection).get_writeback(project_id, proposal_id)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.get_writeback(project_id, proposal_id)

    def create_writeback_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal:
        created_list = self.create_writeback_proposals(project_id, [proposal])
        return created_list[0]

    def create_writeback_proposals(
        self,
        project_id: str,
        proposals: list[WritebackProposalCreate],
        connection: sqlite3.Connection | None = None,
    ) -> list[WritebackProposal]:
        if connection is not None:
            return ReviewRepository(connection).create_writeback_batch(project_id, proposals)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.create_writeback_batch(project_id, proposals)

    def supersede_pending_writebacks_for_target(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        keep_proposal_id: str,
        target_record_id: str,
        reviewed_at: str,
    ) -> int:
        return ReviewRepository(connection).supersede_pending_for_target(
            project_id=project_id,
            keep_proposal_id=keep_proposal_id,
            target_record_id=target_record_id,
            reviewed_at=reviewed_at,
        )

    def supersede_pending_writebacks_for_source(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
    ) -> int:
        return ReviewRepository(connection).supersede_pending_for_source(
            project_id=project_id,
            source_ref=source_ref,
        )

    def update_writeback_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        proposal_status: WritebackProposalStatus,
    ) -> WritebackProposal | None:
        if proposal_status == "accepted":
            return self.accept_writeback_proposal(project_id, proposal_id)
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.update_writeback_status(project_id, proposal_id, proposal_status)

    def accept_writeback_proposal(
        self, project_id: str, proposal_id: str
    ) -> WritebackProposal | None:
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return accept_writeback_proposal(
                uow.connection, project_id=project_id, proposal_id=proposal_id
            )

    def list_reference_suggestions(self, project_id: str) -> list[ReferenceSuggestion]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.list_references(project_id)

    def get_reference_suggestion(
        self, project_id: str, suggestion_id: str
    ) -> ReferenceSuggestion | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.get_reference(project_id, suggestion_id)

    def create_reference_suggestion(
        self, project_id: str, suggestion: ReferenceSuggestionCreate
    ) -> ReferenceSuggestion:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.create_reference(project_id, suggestion)

    def update_reference_suggestion_status(
        self,
        project_id: str,
        suggestion_id: str,
        suggestion_status: ReferenceSuggestionStatus,
    ) -> ReferenceSuggestion | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.review.update_reference_status(project_id, suggestion_id, suggestion_status)

    # ------------------------------------------------------------------
    # Outbox jobs
    # ------------------------------------------------------------------

    def insert_outbox_job(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        job_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
        idempotency_key: str,
    ) -> str:
        """Insert a job inside the caller's transaction (legacy entry point)."""
        return OutboxRepository(connection).insert(
            project_id=project_id,
            job_type=job_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def enqueue_manuscript_revision_index_job(
        self,
        connection: sqlite3.Connection,
        *,
        revision: ManuscriptRevision,
    ) -> str:
        """Enqueue the wiki index job inside the caller's transaction."""
        return enqueue_manuscript_revision_index_job(connection, revision=revision)

    def enqueue_manuscript_revision_analysis_jobs(
        self,
        connection: sqlite3.Connection,
        *,
        revision: ManuscriptRevision,
    ) -> tuple[str, str]:
        """Enqueue both analysis jobs inside the caller's transaction."""
        return enqueue_manuscript_revision_analysis_jobs(connection, revision=revision)

    def get_outbox_job(self, project_id: str, job_id: str) -> OutboxJob | None:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.outbox.get(project_id, job_id)

    def list_outbox_jobs(
        self,
        project_id: str,
        job_status: OutboxJobStatus | None = None,
        limit: int = 100,
        aggregate_type: str | None = None,
    ) -> list[OutboxJob]:
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.outbox.list_jobs(project_id, job_status, limit, aggregate_type)

    def claim_outbox_job(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Atomically claim a pending job (pending -> processing)."""
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.outbox.claim(project_id, job_id)

    def complete_outbox_job(
        self,
        project_id: str,
        job_id: str,
        *,
        succeeded: bool,
        error: str | None = None,
        execution: AnalysisExecution | None = None,
    ) -> OutboxJob | None:
        """Finalize a claimed job; only valid from 'processing'."""
        with SqliteUnitOfWork(self.database_path, write=True) as uow:
            return uow.outbox.complete(
                project_id, job_id, succeeded=succeeded, error=error, execution=execution
            )

    def reset_failed_outbox_job(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Move a failed job back to pending via compare-and-set."""
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.outbox.reset_failed(project_id, job_id)

    def recover_stale_outbox_jobs(self, *, cutoff: str) -> list[OutboxJob]:
        """Reset processing jobs whose lease expired before the cutoff."""
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.outbox.recover_stale(cutoff)

    def list_projects_with_pending_outbox_jobs(self) -> list[str]:
        """Project ids that still hold at least one pending job."""
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.outbox.pending_project_ids()

    # ------------------------------------------------------------------
    # Analysis runs (P1-04)
    # ------------------------------------------------------------------

    def get_analysis_run(
        self,
        project_id: str,
        source_ref: str,
        processor: str,
        input_hash: str | None = None,
    ):
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.analysis.get(project_id, source_ref, processor, input_hash)

    def list_analysis_runs(self, project_id: str, limit: int = 100):
        with SqliteUnitOfWork(self.database_path) as uow:
            return uow.analysis.list_runs(project_id, limit)

    def record_analysis_run(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_ref: str,
        processor: str,
        input_hash: str,
        status: str,
        result_json: dict,
    ):
        """Record a run inside the caller's transaction (legacy entry point)."""
        return AnalysisRepository(connection).record(
            project_id=project_id,
            source_ref=source_ref,
            processor=processor,
            input_hash=input_hash,
            status=status,
            result_json=result_json,
        )
