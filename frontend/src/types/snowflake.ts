import type { WorkflowAgentTrace } from './model'

export type SnowflakeStep = {
  number: number
  title: string
  artifact: string
  description: string
  dependencies: number[]
  optional: boolean
  schema_version: number
  validator_name: string
  virtual: boolean
}

export type SnowflakeRevisionStatus =
  | 'draft'
  | 'pending_review'
  | 'accepted'
  | 'rejected'
  | 'superseded'
  | 'legacy_draft'

export type SnowflakeHeadState = 'missing' | 'approved' | 'stale' | 'skipped'

export type SnowflakeArtifactRevision = {
  id: string
  project_id: string
  step_number: number
  artifact_type: string
  revision_no: number
  source: 'human' | 'ai' | 'legacy' | 'import' | 'restore' | 'derived'
  status: SnowflakeRevisionStatus
  content: string
  structured_payload: Record<string, unknown>
  schema_version: number
  parent_revision_id: string
  base_head_revision_id: string
  upstream_snapshot: Record<string, string>
  review_reason: string
  created_at: string
  reviewed_at: string
}

export type SnowflakeStepState = {
  step: SnowflakeStep
  state: SnowflakeHeadState
  accepted_revision: SnowflakeArtifactRevision | null
  pending_count: number
  stale_reason: string
  stale_trigger_revision_id: string
}

export type SnowflakeRevisionPage = {
  data: SnowflakeArtifactRevision[]
  page: number
  page_size: number
  total_items: number
  total_pages: number
}

export type SnowflakeRecordRevision = {
  id: string
  project_id: string
  step_number: number
  record_id: string
  position: number
  revision_no: number
  source: 'human' | 'ai' | 'legacy' | 'import' | 'restore' | 'derived'
  status: SnowflakeRevisionStatus
  payload: Record<string, unknown>
  base_revision_id: string
  review_reason: string
  created_at: string
  reviewed_at: string
}

export type SnowflakeRecordPage = {
  data: SnowflakeRecordRevision[]
  page: number
  page_size: number
  total_items: number
  total_pages: number
}

export type SnowflakeRevisionDecisionResponse = {
  revision: SnowflakeArtifactRevision
  head: {
    project_id: string
    step_number: number
    accepted_revision_id: string
    state: SnowflakeHeadState
    stale_reason: string
    stale_trigger_revision_id: string
  }
  affected_steps: number[]
  outbox_job_id: string
}

export type SnowflakeManuscriptProgress = {
  project_id: string
  total_scene_contracts: number
  pending_manuscript_proposals: number
  accepted_latest_revisions: number
  stale_scene_count: number
  completion_percent: number
  complete: boolean
}

export type SnowflakeArtifact = {
  project_id: string
  step_number: number
  artifact: string
  content: string
}

export type SnowflakeGenerationResponse = SnowflakeArtifact & {
  workflow_trace: WorkflowAgentTrace[]
  revision: SnowflakeArtifactRevision | null
  record_revisions: SnowflakeRecordRevision[]
}
