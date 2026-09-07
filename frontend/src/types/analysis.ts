import type { WritebackProposal } from './writeback'

export type DirectorReport = {
  project_id: string; scene_id: string; scene_sequence: number
  findings: { code: string; severity: string; title: string; detail: string; advisory: boolean }[]
  thread_lifecycles: { thread_id: string; status: string; detail: string }[]
}

export type OutboxJobType = 'llm_wiki_ingest' | 'consistency_analysis' | 'writeback_analysis' | 'clp_extraction'

export type OutboxJobStatus = 'pending' | 'processing' | 'succeeded' | 'failed'

export type OutboxJob = {
  processing_started_at: string
  id: string
  project_id: string
  job_type: OutboxJobType
  aggregate_type: string
  aggregate_id: string
  payload: Record<string, unknown>
  status: OutboxJobStatus
  attempt_count: number
  last_error: string
  created_at: string
  completed_at: string
}

export type FindingSeverity = 'info' | 'warning' | 'critical'

export type ConsistencyFinding = {
  id: string
  severity: FindingSeverity
  rule_code: string
  title: string
  description: string
  manuscript_source_ref: string
  manuscript_excerpt: string
  canon_entity_id: string | null
  canon_field: string | null
  expected_value: string
  observed_value: string
  suggested_action: string
  confidence: 'exact' | 'heuristic'
}

export type ConsistencyReportSummary = {
  finding_count: number
  critical_count: number
  warning_count: number
  info_count: number
}

export type ConsistencyReport = {
  project_id: string
  source_ref: string
  processor: string
  cached: boolean
  run_id: string
  run_version: number
  summary: ConsistencyReportSummary
  findings: ConsistencyFinding[]
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
