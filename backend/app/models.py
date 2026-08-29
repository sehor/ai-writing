from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CanonEntityType = Literal["character", "location", "item", "faction", "rule"]
MemoryRecordType = Literal[
    "chapter_summary",
    "prose_sample",
    "voice_sample",
    "style_rule",
]
GraphNodeType = Literal[
    "project",
    "snowflake_artifact",
    "canon_entity",
    "scene",
    "memory_record",
    "story_thread",
]
GraphEdgeType = Literal["contains", "depends_on", "references", "informs"]
GraphRiskSeverity = Literal["info", "warning", "critical"]
WorkflowRuntimeType = Literal["local_deterministic", "provider_deepseek"]
ManuscriptProposalSource = Literal["scene_contract"]
ManuscriptProposalStatus = Literal["pending_review", "accepted", "rejected", "superseded"]
WritebackTarget = Literal["canon_entity", "memory_record"]
WritebackAction = Literal["create", "update"]
WritebackProposalStatus = Literal["pending_review", "accepted", "rejected", "superseded"]
ReferenceScopeType = Literal[
    "project",
    "snowflake_step",
    "scene",
    "canon_entity",
    "memory_record",
    "manuscript_scene",
    "graph",
]
ReferenceSuggestionType = Literal[
    "brainstorm",
    "scene_bridge",
    "conflict_options",
    "character_motivation",
    "canon_gap",
    "prose_reference",
    "structure_fix",
]
ReferenceSuggestionStatus = Literal["pending_review", "accepted", "rejected", "superseded"]
HermesProcessStatus = Literal["completed", "partial", "failed"]
HermesWikiChangeAction = Literal["created", "updated", "skipped"]
HermesIssueSeverity = Literal["info", "warning", "error"]
StoryFactStatus = Literal["planned", "confirmed", "superseded"]
KnowledgeScope = Literal["world_truth", "reader_knowledge", "character_knowledge"]
NarrativeRelationStatus = Literal["planned", "confirmed", "superseded"]
StoryThreadType = Literal["foreshadow", "mystery", "relationship", "conflict", "promise", "subplot"]
StoryThreadStatus = Literal["planned", "planted", "developing", "dormant", "paid_off", "abandoned"]
StoryThreadAction = Literal["plant", "reinforce", "misdirect", "escalate", "partial_payoff", "payoff"]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "ai-writing-backend"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    premise: str = Field(min_length=1, max_length=500)

    @field_validator("title", "premise")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class ProjectSummary(BaseModel):
    id: str
    title: str
    premise: str
    current_step: int = Field(ge=1, le=10)


class SnowflakeStep(BaseModel):
    number: int = Field(ge=1, le=10)
    title: str
    artifact: str
    description: str


class SnowflakeGenerationRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    step_number: int = Field(ge=1, le=10)
    user_input: str = Field(min_length=1, max_length=4000)

    @field_validator("project_id", "user_input")
    @classmethod
    def normalize_generation_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class SnowflakeArtifactUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class SnowflakeArtifact(BaseModel):
    project_id: str
    step_number: int = Field(ge=1, le=10)
    artifact: str
    content: str


class WorkflowAgentTrace(BaseModel):
    stage: str
    agent_name: str
    status: str


class WorkflowRuntimeStatus(BaseModel):
    runtime: WorkflowRuntimeType
    provider: str
    provider_configured: bool
    model: str = ""
    base_url: str = ""
    details: str = ""


class SnowflakeGenerationResponse(BaseModel):
    project_id: str
    step_number: int = Field(ge=1, le=10)
    artifact: str
    content: str
    workflow_trace: list[WorkflowAgentTrace] = Field(default_factory=list)


class CanonEntityCreate(BaseModel):
    entity_type: CanonEntityType
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=1000)
    current_state: str = Field(default="", max_length=4000)
    constraints: str = Field(default="", max_length=4000)
    last_seen: str = Field(default="", max_length=120)
    timeline_notes: str = Field(default="", max_length=8000)

    @field_validator(
        "name",
        "summary",
        "current_state",
        "constraints",
        "last_seen",
        "timeline_notes",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class CanonEntityUpdate(CanonEntityCreate):
    pass


class CanonEntity(CanonEntityCreate):
    id: str
    project_id: str
    version: int = Field(default=1, ge=1)
    updated_at: str = ""


class StoryFactCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    predicate: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=4000)
    valid_from_scene: int = Field(ge=0, le=999)
    valid_to_scene: int | None = Field(default=None, ge=0, le=999)
    reader_visible_from: int | None = Field(default=None, ge=0, le=999)
    source_ref: str = Field(default="", max_length=240)
    status: StoryFactStatus = "confirmed"

    @field_validator("subject", "predicate", "value", "source_ref")
    @classmethod
    def normalize_story_fact_text(cls, value: str) -> str:
        return value.strip()


class StoryFact(StoryFactCreate):
    id: str
    project_id: str


class KnowledgeStateCreate(BaseModel):
    scope: KnowledgeScope
    character: str = Field(default="", max_length=160)
    known_from_scene: int = Field(ge=0, le=999)
    source_ref: str = Field(default="", max_length=240)
    status: StoryFactStatus = "confirmed"

    @field_validator("character", "source_ref")
    @classmethod
    def normalize_knowledge_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_scope_subject(self) -> "KnowledgeStateCreate":
        if self.scope == "character_knowledge" and not self.character:
            raise ValueError("character is required for character_knowledge")
        if self.scope != "character_knowledge" and self.character:
            raise ValueError("character is only valid for character_knowledge")
        return self


class KnowledgeState(KnowledgeStateCreate):
    id: str
    fact_id: str
    project_id: str


class CharacterKnowledgeCreate(BaseModel):
    character: str = Field(min_length=1, max_length=160)
    known_from_scene: int = Field(ge=0, le=999)

    @field_validator("character")
    @classmethod
    def normalize_character_name(cls, value: str) -> str:
        return value.strip()


class CharacterKnowledge(CharacterKnowledgeCreate):
    fact_id: str
    project_id: str


class NarrativeRelationCreate(BaseModel):
    source: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=240)
    relation: str = Field(min_length=1, max_length=160)
    valid_from: int = Field(ge=0, le=999)
    valid_to: int | None = Field(default=None, ge=0, le=999)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_ref: str = Field(default="", max_length=240)
    status: NarrativeRelationStatus = "confirmed"

    @field_validator("source", "target", "relation", "source_ref")
    @classmethod
    def normalize_narrative_relation_text(cls, value: str) -> str:
        return value.strip()


class NarrativeRelation(NarrativeRelationCreate):
    id: str
    project_id: str


class StoryStateResponse(BaseModel):
    project_id: str
    scene_position: int
    character: str = ""
    world_truth: list[StoryFact] = Field(default_factory=list)
    reader_knowledge: list[StoryFact] = Field(default_factory=list)
    character_knowledge: list[StoryFact] = Field(default_factory=list)


class StoryThreadCreate(BaseModel):
    thread_type: StoryThreadType
    title: str = Field(min_length=1, max_length=240)
    status: StoryThreadStatus = "planned"
    planted_at: int | None = Field(default=None, ge=0, le=999)
    target_payoff_from: int | None = Field(default=None, ge=0, le=999)
    target_payoff_to: int | None = Field(default=None, ge=0, le=999)
    importance: int = Field(default=3, ge=1, le=5)
    reveal_constraints: str = Field(default="", max_length=4000)

    @field_validator("title", "reveal_constraints")
    @classmethod
    def normalize_story_thread_text(cls, value: str) -> str:
        return value.strip()


class StoryThread(StoryThreadCreate):
    id: str
    project_id: str


class StoryThreadStatusUpdate(BaseModel):
    status: StoryThreadStatus


class StoryThreadEventCreate(BaseModel):
    scene_id: str = Field(min_length=1, max_length=160)
    action: StoryThreadAction
    note: str = Field(default="", max_length=2000)

    @field_validator("scene_id", "note")
    @classmethod
    def normalize_story_thread_event_text(cls, value: str) -> str:
        return value.strip()


class StoryThreadEvent(StoryThreadEventCreate):
    id: str
    project_id: str
    thread_id: str


class SceneContractCreate(BaseModel):
    chapter_id: str = Field(default="", max_length=160)
    sequence: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=160)
    pov: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=1000)
    conflict: str = Field(default="", max_length=1000)
    turning_point: str = Field(default="", max_length=1000)
    required_canon: str = Field(default="", max_length=4000)
    forbidden_facts: str = Field(default="", max_length=4000)
    open_threads: str = Field(default="", max_length=4000)
    source_artifact_step: int = Field(default=8, ge=1, le=10)

    @field_validator(
        "chapter_id",
        "title",
        "pov",
        "goal",
        "conflict",
        "turning_point",
        "required_canon",
        "forbidden_facts",
        "open_threads",
    )
    @classmethod
    def normalize_scene_text(cls, value: str) -> str:
        return value.strip()


class SceneContractUpdate(SceneContractCreate):
    pass


class SceneContract(SceneContractCreate):
    id: str
    project_id: str


class ManuscriptChapterCreate(BaseModel):
    sequence: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=2000)

    @field_validator("title", "summary")
    @classmethod
    def normalize_chapter_text(cls, value: str) -> str:
        return value.strip()


class ManuscriptChapterUpdate(ManuscriptChapterCreate):
    pass


class ManuscriptChapter(ManuscriptChapterCreate):
    id: str
    project_id: str


class ChapterCompileResponse(BaseModel):
    project_id: str
    scene_id: str
    context: str
    draft: str
    checklist: list[str] = Field(default_factory=list)


class ManuscriptProposalCreate(BaseModel):
    scene_id: str = Field(min_length=1, max_length=160)
    source: ManuscriptProposalSource = "scene_contract"
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)
    context: str = Field(default="", max_length=60000)
    checklist: list[str] = Field(default_factory=list)

    @field_validator("scene_id", "title", "content", "context")
    @classmethod
    def normalize_proposal_text(cls, value: str) -> str:
        return value.strip()


class ManuscriptProposalStatusUpdate(BaseModel):
    status: ManuscriptProposalStatus


class ManuscriptProposal(ManuscriptProposalCreate):
    id: str
    project_id: str
    status: ManuscriptProposalStatus = "pending_review"
    created_at: str
    reviewed_at: str = ""


class ManuscriptScene(BaseModel):
    id: str
    project_id: str
    scene_id: str
    proposal_id: str
    title: str
    content: str
    version: int = Field(ge=1)
    accepted_at: str


class ManuscriptSceneUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)

    @field_validator("title", "content")
    @classmethod
    def normalize_scene_update_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class ManuscriptRevision(BaseModel):
    id: str
    project_id: str
    scene_id: str
    proposal_id: str
    title: str
    content: str
    version: int = Field(ge=1)
    created_at: str


class ManuscriptRevisionDiff(BaseModel):
    project_id: str
    left_revision_id: str
    right_revision_id: str
    left_title: str
    right_title: str
    diff_lines: list[str] = Field(default_factory=list)


class ManuscriptExportResponse(BaseModel):
    project_id: str
    title: str
    scene_count: int
    content: str
    generated_at: str


class WikiExportFile(BaseModel):
    path: str
    content_type: str
    content: str


class WikiExportResponse(BaseModel):
    project_id: str
    title: str
    file_count: int
    generated_at: str
    files: list[WikiExportFile] = Field(default_factory=list)


class MemoryRecordCreate(BaseModel):
    record_type: MemoryRecordType
    title: str = Field(min_length=1, max_length=160)
    scope: str = Field(default="", max_length=160)
    content: str = Field(min_length=1, max_length=12000)
    tags: str = Field(default="", max_length=1000)
    source_ref: str = Field(default="", max_length=160)

    @field_validator("title", "scope", "content", "tags", "source_ref")
    @classmethod
    def normalize_memory_text(cls, value: str) -> str:
        return value.strip()


class MemoryRecordUpdate(MemoryRecordCreate):
    pass


class MemoryRecord(MemoryRecordCreate):
    id: str
    project_id: str


class WritebackProposalCreate(BaseModel):
    target: WritebackTarget
    action: WritebackAction = "create"
    title: str = Field(min_length=1, max_length=160)
    rationale: str = Field(default="", max_length=4000)
    payload: dict = Field(default_factory=dict)
    source_ref: str = Field(default="", max_length=160)
    # Update proposals carry an optimistic-concurrency handle on the
    # existing record plus field-level before/after changes.
    target_record_id: str = Field(default="", max_length=160)
    expected_version: int | None = Field(default=None, ge=1)
    changes: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("title", "rationale", "source_ref", "target_record_id")
    @classmethod
    def normalize_writeback_text(cls, value: str) -> str:
        return value.strip()


class WritebackProposalStatusUpdate(BaseModel):
    status: WritebackProposalStatus


class WritebackProposal(WritebackProposalCreate):
    id: str
    project_id: str
    status: WritebackProposalStatus = "pending_review"
    created_at: str
    reviewed_at: str = ""
    applied_record_id: str = ""


class ReferenceGenerationRequest(BaseModel):
    suggestion_type: ReferenceSuggestionType = "brainstorm"
    scope_type: ReferenceScopeType = "project"
    scope_ref: str = Field(default="", max_length=160)
    author_problem: str = Field(min_length=1, max_length=4000)
    desired_output: str = Field(default="", max_length=1000)

    @field_validator("scope_ref", "author_problem", "desired_output")
    @classmethod
    def normalize_reference_request_text(cls, value: str) -> str:
        return value.strip()


class ReferenceSuggestionCreate(BaseModel):
    suggestion_type: ReferenceSuggestionType
    scope_type: ReferenceScopeType
    scope_ref: str = Field(default="", max_length=160)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)
    rationale: str = Field(default="", max_length=4000)
    used_context: str = Field(default="", max_length=60000)
    canon_warnings: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    graph_warnings: list[str] = Field(default_factory=list)
    proposed_writebacks: list[WritebackProposalCreate] = Field(default_factory=list)
    workflow_trace: list[WorkflowAgentTrace] = Field(default_factory=list)

    @field_validator("scope_ref", "title", "content", "rationale", "used_context")
    @classmethod
    def normalize_reference_suggestion_text(cls, value: str) -> str:
        return value.strip()


class ReferenceSuggestionStatusUpdate(BaseModel):
    status: ReferenceSuggestionStatus


class ReferenceSuggestion(ReferenceSuggestionCreate):
    id: str
    project_id: str
    status: ReferenceSuggestionStatus = "pending_review"
    created_at: str
    reviewed_at: str = ""


class HermesWikiChange(BaseModel):
    path: str
    action: HermesWikiChangeAction
    reason: str = ""


class HermesProcessingIssue(BaseModel):
    severity: HermesIssueSeverity
    code: str
    message: str
    source_ref: str = ""


class HermesRevisionProcessResult(BaseModel):
    status: HermesProcessStatus
    summary: str
    wiki_changes: list[HermesWikiChange] = Field(default_factory=list)
    issues: list[HermesProcessingIssue] = Field(default_factory=list)
    writeback_proposals: list[WritebackProposalCreate] = Field(default_factory=list)
    processed_source_ref: str


class HermesRevisionProcessResponse(BaseModel):
    status: HermesProcessStatus
    summary: str
    wiki_changes: list[HermesWikiChange] = Field(default_factory=list)
    issues: list[HermesProcessingIssue] = Field(default_factory=list)
    writeback_proposals: list[WritebackProposal] = Field(default_factory=list)
    processed_source_ref: str
    cached: bool = False
    analysis_run_id: str = ""


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: GraphNodeType
    status: str = ""


class GraphEdge(BaseModel):
    source: str
    target: str
    edge_type: GraphEdgeType
    label: str = ""


class GraphRisk(BaseModel):
    id: str
    severity: GraphRiskSeverity
    title: str
    detail: str
    source_id: str = ""


class GraphAnalysisSummary(BaseModel):
    node_count: int
    edge_count: int
    risk_count: int
    critical_count: int
    warning_count: int
    unresolved_thread_count: int
    canon_reference_count: int


class GraphAnalysisResponse(BaseModel):
    project_id: str
    summary: GraphAnalysisSummary
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    risks: list[GraphRisk] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Structured Snowflake compiler (P1-05)
# ---------------------------------------------------------------------------


SceneProposalStatus = ManuscriptProposalStatus


class SceneProposalCreate(BaseModel):
    """A parsed Step 8 scene awaiting batch review."""

    sequence: int = Field(ge=1, le=999)
    chapter_id: str = Field(default="", max_length=160)
    chapter_hint: str = Field(default="", max_length=160)
    title: str = Field(min_length=1, max_length=160)
    pov: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=1000)
    conflict: str = Field(default="", max_length=1000)
    turning_point: str = Field(default="", max_length=1000)
    required_canon_ids: str = Field(default="", max_length=2000)
    required_canon_raw: str = Field(default="", max_length=4000)
    forbidden_fact_refs: str = Field(default="", max_length=4000)
    open_threads: str = Field(default="", max_length=4000)
    source_ref: str = Field(default="", max_length=160)
    source_excerpt: str = Field(default="", max_length=2000)
    warnings: list[str] = Field(default_factory=list)

    @field_validator(
        "chapter_id",
        "chapter_hint",
        "title",
        "pov",
        "goal",
        "conflict",
        "turning_point",
        "required_canon_ids",
        "required_canon_raw",
        "forbidden_fact_refs",
        "open_threads",
        "source_ref",
    )
    @classmethod
    def normalize_scene_proposal_text(cls, value: str) -> str:
        return value.strip()


class SceneProposal(SceneProposalCreate):
    id: str
    project_id: str
    status: SceneProposalStatus = "pending_review"
    applied_scene_id: str = ""
    created_at: str
    reviewed_at: str = ""


class SceneProposalStatusUpdate(BaseModel):
    status: SceneProposalStatus


class SceneProposalAcceptRequest(BaseModel):
    """Empty proposal_ids accepts every pending proposal for the project."""

    proposal_ids: list[str] = Field(default_factory=list)


class CompileRunInfo(BaseModel):
    run_id: str
    run_version: int
    cached: bool


class CanonExtractionReport(BaseModel):
    """Step 7 artifact compiled into Canon create / update proposals."""

    project_id: str
    step_number: int
    processor: str
    cached: bool
    run_id: str
    run_version: int
    warnings: list[str] = Field(default_factory=list)
    proposals: list[WritebackProposal] = Field(default_factory=list)


class SceneParseReport(BaseModel):
    """Step 8 artifact parsed into reviewable Scene Contract proposals."""

    project_id: str
    step_number: int
    processor: str
    cached: bool
    run_id: str
    run_version: int
    warnings: list[str] = Field(default_factory=list)
    proposals: list[SceneProposal] = Field(default_factory=list)


class SceneProposalAcceptanceReport(BaseModel):
    project_id: str
    scenes: list[SceneContract] = Field(default_factory=list)
    proposals: list[SceneProposal] = Field(default_factory=list)
