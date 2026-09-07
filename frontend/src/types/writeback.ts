export type ReviewStatus = 'pending_review' | 'accepted' | 'rejected' | 'superseded'

export type WritebackProposalStatus = ReviewStatus

export type WritebackTarget =
  | 'canon_entity'
  | 'memory_record'
  | 'narrative_relation'
  | 'story_thread'
  | 'story_thread_event'
  | 'story_thread_status'

export type WritebackFieldChange = {
  before: string
  after: string
}

export type WritebackProposal = {
  id: string
  project_id: string
  target: WritebackTarget
  action: 'create' | 'update'
  title: string
  rationale: string
  payload: Record<string, unknown>
  source_ref: string
  target_record_id: string
  expected_version: number | null
  changes: Record<string, WritebackFieldChange>
  status: WritebackProposalStatus
  created_at: string
  reviewed_at: string
  applied_record_id: string
}

// P1-07: outbox jobs surfaced in the UI (post-acceptance analysis status).
