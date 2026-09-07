import type { SceneContract } from './scene'
import type { ReviewStatus, WritebackProposal } from './writeback'

export type SceneProposalStatus = ReviewStatus

// P1-05: structured Snowflake compiler (Step 7 -> Canon proposals, Step 8 -> scene proposals)

export type SceneProposal = {
  operation?: 'create' | 'update'
  source_record_id?: string
  source_record_revision_id?: string
  target_scene_id?: string
  expected_plan_version?: number
  changes?: Record<string, { before: string | number; after: string | number }>
  id: string
  project_id: string
  sequence: number
  chapter_id: string
  chapter_hint: string
  title: string
  pov: string
  goal: string
  conflict: string
  turning_point: string
  outcome: string
  required_canon_ids: string
  required_canon_raw: string
  forbidden_fact_refs: string
  information_delta: string
  character_state_delta: string
  story_thread_actions: string
  open_threads: string
  source_ref: string
  source_excerpt: string
  warnings: string[]
  blocking_errors: string[]
  status: SceneProposalStatus
  applied_scene_id: string
  created_at: string
  reviewed_at: string
}

export type CompileRunInfo = {
  run_id: string
  run_version: number
  cached: boolean
}

export type CanonExtractionReport = {
  project_id: string
  step_number: number
  processor: string
  cached: boolean
  run_id: string
  run_version: number
  warnings: string[]
  proposals: WritebackProposal[]
}

export type SceneParseReport = {
  project_id: string
  step_number: number
  processor: string
  cached: boolean
  run_id: string
  run_version: number
  warnings: string[]
  proposals: SceneProposal[]
  thread_proposals: WritebackProposal[]
}

export type SceneProposalAcceptanceReport = {
  project_id: string
  scenes: SceneContract[]
  proposals: SceneProposal[]
}
