import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const reviewsStore = read('../src/stores/reviews.ts')
const manuscriptStore = read('../src/stores/manuscript.ts')
const revisionHistory = read('../src/components/manuscript/RevisionHistory.vue')
const types = read('../src/types/index.ts')

test('store tracks post-acceptance analysis jobs scoped to the active project', () => {
  assert.match(reviewsStore, /const postAcceptJobs = ref<OutboxJob\[\]>\(\[\]\)/)
  // Jobs come from the outbox endpoint and are filtered to analysis types
  // (including the wiki index job, which is retryable from the same panel).
  assert.match(reviewsStore, /\/projects\/\$\{projectId\}\/outbox-jobs/)
  assert.match(reviewsStore, /'llm_wiki_ingest',\s*'consistency_analysis',\s*'writeback_analysis',/)
  assert.match(reviewsStore, /async function loadPostAcceptAnalysisJobs\(/)
  assert.match(reviewsStore, /async function retryPostAcceptAnalysisJob\(/)
  // Stale results are dropped when the user switches projects mid-request.
  assert.match(
    reviewsStore,
    /const jobs: OutboxJob\[\] = await response\.json\(\)\r?\n\s+if \(!isActiveProject\(projectId\)\)/,
  )
})

test('accepting a proposal surfaces automatic analyses without a manual run', () => {
  // Acceptance orchestration lives in the manuscript store's proposal action.
  assert.match(
    manuscriptStore,
    /reviews\.loadPostAcceptAnalysisJobs\(projectId\),\r?\n\s+reviews\.showLatestConsistencyReport\(projectId\),/,
  )
  // The report is fetched through the replay GET route, never auto-created state.
  assert.match(reviewsStore, /analysis\/consistency\/from-revision\/\$\{revision\.id\}/)
  assert.match(reviewsStore, /postAcceptJobs\.value = \[\]/)
})

test('revision history renders analysis job status with retry for failures', () => {
  assert.match(revisionHistory, /class="post-accept-analysis"/)
  assert.match(revisionHistory, /analysisJobLabel\(job\.job_type\)/)
  assert.match(revisionHistory, /job\.status/)
  assert.match(revisionHistory, /job\.last_error/)
  assert.match(revisionHistory, /retryPostAcceptAnalysisJob\(job\.id\)/)
  assert.match(revisionHistory, /loadPostAcceptAnalysisJobs\(\)/)
})

test('outbox job types mirror the backend contract', () => {
  assert.match(types, /export type OutboxJobType = 'llm_wiki_ingest' \| 'consistency_analysis' \| 'writeback_analysis'/)
  assert.match(
    types,
    /export type OutboxJobStatus = 'pending' \| 'processing' \| 'succeeded' \| 'failed'/,
  )
  assert.match(types, /export type OutboxJob = \{/)
  assert.match(types, /aggregate_id: string/)
  assert.match(types, /attempt_count: number/)
})
