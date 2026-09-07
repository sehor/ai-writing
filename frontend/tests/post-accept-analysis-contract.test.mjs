import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const reviewsStore = read('../src/stores/reviews.ts')
const manuscriptStore = read('../src/stores/manuscript.ts')
const revisionHistory = read('../src/components/manuscript/RevisionHistory.vue')
const types = read('../src/types/analysis.ts')
const jobsStore = read('../src/stores/analysisJobs.ts')

test('store tracks post-acceptance analysis jobs scoped to the active project', () => {
  assert.match(jobsStore, /const jobs = ref<OutboxJob\[\]>\(\[\]\)/)
  assert.match(jobsStore, /outbox-jobs\?aggregate_type=manuscript_revision&limit=/)
  assert.match(jobsStore, /clp_extraction: 'CLP extraction'/)
  assert.doesNotMatch(jobsStore, /from ['"]\.\/workspace/)
  assert.match(reviewsStore, /async function loadPostAcceptAnalysisJobs\(/)
  assert.match(reviewsStore, /async function retryPostAcceptAnalysisJob\(/)
  // Polling, project switching and retry behavior are exercised in analysis-jobs.test.ts.
  assert.match(jobsStore, /controller\.abort\(\)/)
})

test('accepting a proposal surfaces automatic analyses without a manual run', () => {
  // Acceptance orchestration lives in the manuscript store's proposal action.
  assert.match(
    manuscriptStore,
    /reviewPort\?\.loadPostAcceptAnalysisJobs\(projectId\),\r?\n\s+reviewPort\?\.showLatestConsistencyReport\(projectId\),/,
  )
  // The report is fetched through the replay GET route, never auto-created state.
  assert.match(reviewsStore, /analysis\/consistency\/from-revision\/\$\{revision\.id\}/)
  assert.match(reviewsStore, /analysisJobs\.stop\(\)/)
})

// All three commit paths are exercised in manuscript-composition.test.ts.

test('revision history renders analysis job status with retry for failures', () => {
  assert.match(revisionHistory, /class="post-accept-analysis"/)
  assert.match(revisionHistory, /analysisJobLabel\(job\.job_type\)/)
  assert.match(revisionHistory, /job\.status/)
  assert.match(revisionHistory, /job\.last_error/)
  assert.match(revisionHistory, /retryPostAcceptAnalysisJob\(job\.id\)/)
  assert.match(revisionHistory, /loadPostAcceptAnalysisJobs\(\)/)
})

test('outbox job types mirror the backend contract', () => {
  assert.match(types, /export type OutboxJobType = 'llm_wiki_ingest' \| 'consistency_analysis' \| 'writeback_analysis' \| 'clp_extraction'/)
  assert.match(
    types,
    /export type OutboxJobStatus = 'pending' \| 'processing' \| 'succeeded' \| 'failed'/,
  )
  assert.match(types, /export type OutboxJob = \{/)
  assert.match(types, /aggregate_id: string/)
  assert.match(types, /attempt_count: number/)
})
