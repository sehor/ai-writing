export type ProjectSummary = {
  id: string
  title: string
  premise: string
  current_step: number
}

export type SnowflakeStep = {
  number: number
  title: string
  artifact: string
  description: string
}

export type SnowflakeArtifact = {
  project_id: string
  step_number: number
  artifact: string
  content: string
}

export type WorkflowAgentTrace = {
  stage: string
  agent_name: string
  status: string
}

export type SnowflakeGenerationResponse = SnowflakeArtifact & {
  workflow_trace: WorkflowAgentTrace[]
}

export type CanonEntityType = 'character' | 'location' | 'item' | 'faction' | 'rule'

export type CanonEntity = {
  id: string
  project_id: string
  entity_type: CanonEntityType
  name: string
  summary: string
  current_state: string
  constraints: string
  last_seen: string
  timeline_notes: string
}

export type CanonDraft = Omit<CanonEntity, 'id' | 'project_id'>

export type SceneContract = {
  id: string
  project_id: string
  chapter_id: string
  sequence: number
  title: string
  pov: string
  goal: string
  conflict: string
  turning_point: string
  required_canon: string
  forbidden_facts: string
  open_threads: string
  source_artifact_step: number
}

export type SceneDraft = Omit<SceneContract, 'id' | 'project_id'>

export type ManuscriptChapter = {
  id: string
  project_id: string
  sequence: number
  title: string
  summary: string
}

export type ManuscriptChapterDraft = Omit<ManuscriptChapter, 'id' | 'project_id'>

export type MemoryRecordType = 'chapter_summary' | 'prose_sample' | 'voice_sample' | 'style_rule'

export type MemoryRecord = {
  id: string
  project_id: string
  record_type: MemoryRecordType
  title: string
  scope: string
  content: string
  tags: string
  source_ref: string
}

export type MemoryDraft = Omit<MemoryRecord, 'id' | 'project_id'>

export type ChapterCompileResponse = {
  project_id: string
  scene_id: string
  context: string
  draft: string
  checklist: string[]
}

export type ManuscriptProposalStatus = 'pending_review' | 'accepted' | 'rejected'

export type ManuscriptProposal = {
  id: string
  project_id: string
  scene_id: string
  source: 'scene_contract'
  title: string
  content: string
  context: string
  checklist: string[]
  status: ManuscriptProposalStatus
  created_at: string
  reviewed_at: string
}

export type ManuscriptScene = {
  id: string
  project_id: string
  scene_id: string
  proposal_id: string
  title: string
  content: string
  version: number
  accepted_at: string
}

export type ManuscriptRevision = {
  id: string
  project_id: string
  scene_id: string
  proposal_id: string
  title: string
  content: string
  version: number
  created_at: string
}

export type ManuscriptRevisionDiff = {
  project_id: string
  left_revision_id: string
  right_revision_id: string
  left_title: string
  right_title: string
  diff_lines: string[]
}

export type ManuscriptExport = {
  project_id: string
  title: string
  scene_count: number
  content: string
  generated_at: string
}

export type WritebackProposalStatus = 'pending_review' | 'accepted' | 'rejected'
export type WritebackTarget = 'canon_entity' | 'memory_record'
export type ReferenceSuggestionStatus = 'pending_review' | 'accepted' | 'rejected'
export type ReferenceScopeType =
  | 'project'
  | 'snowflake_step'
  | 'scene'
  | 'canon_entity'
  | 'memory_record'
  | 'manuscript_scene'
  | 'graph'
export type ReferenceSuggestionType =
  | 'brainstorm'
  | 'scene_bridge'
  | 'conflict_options'
  | 'character_motivation'
  | 'canon_gap'
  | 'prose_reference'
  | 'structure_fix'

export type WritebackProposal = {
  id: string
  project_id: string
  target: WritebackTarget
  action: 'create'
  title: string
  rationale: string
  payload: Record<string, unknown>
  source_ref: string
  status: WritebackProposalStatus
  created_at: string
  reviewed_at: string
  applied_record_id: string
}

export type ReferenceSuggestion = {
  id: string
  project_id: string
  suggestion_type: ReferenceSuggestionType
  scope_type: ReferenceScopeType
  scope_ref: string
  title: string
  content: string
  rationale: string
  used_context: string
  canon_warnings: string[]
  style_notes: string[]
  graph_warnings: string[]
  proposed_writebacks: WritebackProposal[]
  workflow_trace: WorkflowAgentTrace[]
  status: ReferenceSuggestionStatus
  created_at: string
  reviewed_at: string
}

export type ReferenceDraft = {
  suggestion_type: ReferenceSuggestionType
  scope_type: ReferenceScopeType
  scope_ref: string
  author_problem: string
  desired_output: string
}

export type HermesWikiChange = {
  path: string
  action: 'created' | 'updated' | 'skipped'
  reason: string
}

export type HermesProcessingIssue = {
  severity: 'info' | 'warning' | 'error'
  code: string
  message: string
  source_ref: string
}

export type HermesRevisionProcessResponse = {
  status: 'completed' | 'partial' | 'failed'
  summary: string
  wiki_changes: HermesWikiChange[]
  issues: HermesProcessingIssue[]
  writeback_proposals: WritebackProposal[]
  processed_source_ref: string
}

export type GraphNode = {
  id: string
  label: string
  node_type: string
  status: string
}

export type GraphEdge = {
  source: string
  target: string
  edge_type: string
  label: string
}

export type GraphRisk = {
  id: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  detail: string
  source_id: string
}

export type GraphAnalysisSummary = {
  node_count: number
  edge_count: number
  risk_count: number
  critical_count: number
  warning_count: number
  unresolved_thread_count: number
  canon_reference_count: number
}

export type GraphAnalysisResponse = {
  project_id: string
  summary: GraphAnalysisSummary
  nodes: GraphNode[]
  edges: GraphEdge[]
  risks: GraphRisk[]
}

export type WorkflowRuntimeStatus = {
  runtime: 'local_deterministic' | 'provider_deepseek'
  provider: string
  provider_configured: boolean
  model: string
  base_url: string
  details: string
}

export type ActiveSection = 'snowflake' | 'canon' | 'memory' | 'graph' | 'manuscript'
