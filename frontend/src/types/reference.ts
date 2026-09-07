import type { WorkflowAgentTrace } from './model'
import type { ReviewStatus, WritebackProposal } from './writeback'

export type ReferenceSuggestionStatus = ReviewStatus

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
