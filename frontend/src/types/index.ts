// Compatibility exports. Domain modules import each other directly.

export type {
  DirectorReport,
  OutboxJobType,
  OutboxJobStatus,
  OutboxJob,
  FindingSeverity,
  ConsistencyFinding,
  ConsistencyReportSummary,
  ConsistencyReport,
  HermesWikiChange,
  HermesProcessingIssue,
  HermesRevisionProcessResponse,
} from './analysis'

export type {
  CanonEntityType,
  CanonEntity,
  CanonDraft,
} from './canon'

export type {
  SceneProposalStatus,
  SceneProposal,
  CompileRunInfo,
  CanonExtractionReport,
  SceneParseReport,
  SceneProposalAcceptanceReport,
} from './compiler'

export type {
  GraphNode,
  GraphEdge,
  GraphRisk,
  GraphAnalysisSummary,
  GraphAnalysisResponse,
} from './graph'

export type {
  ManuscriptChapter,
  ManuscriptChapterDraft,
  ChapterCompileResponse,
  ManuscriptProposalStatus,
  ManuscriptGenerationReview,
  ManuscriptProposal,
  ManuscriptScene,
  ManuscriptRevision,
  ManuscriptRevisionDiff,
  ManuscriptExport,
} from './manuscript'

export type {
  MemoryRecordType,
  MemoryRecord,
  MemoryDraft,
} from './memory'

export type {
  WorkflowAgentTrace,
  WorkflowRuntimeStatus,
  ModelCapabilities,
  ModelProfile,
  ModelExecutionOptions,
} from './model'

export type {
  StoryFactStatus,
  KnowledgeScope,
  StoryFact,
  KnowledgeState,
  NarrativeRevision,
  StoryThreadStatus,
  StoryThread,
  NarrativeRelation,
} from './narrative'

export type {
  ProjectSummary,
  ActiveSection,
  BackupPreviewSummary,
  BackupImportSummary,
} from './project'

export type {
  ReferenceSuggestionStatus,
  ReferenceScopeType,
  ReferenceSuggestionType,
  ReferenceSuggestion,
  ReferenceDraft,
} from './reference'

export type {
  SceneContract,
  SceneDraft,
} from './scene'

export type {
  SnowflakeStep,
  SnowflakeRevisionStatus,
  SnowflakeHeadState,
  SnowflakeArtifactRevision,
  SnowflakeStepState,
  SnowflakeRevisionPage,
  SnowflakeRecordRevision,
  SnowflakeRecordPage,
  SnowflakeRevisionDecisionResponse,
  SnowflakeManuscriptProgress,
  SnowflakeArtifact,
  SnowflakeGenerationResponse,
} from './snowflake'

export type {
  ReviewStatus,
  WritebackProposalStatus,
  WritebackTarget,
  WritebackFieldChange,
  WritebackProposal,
} from './writeback'
