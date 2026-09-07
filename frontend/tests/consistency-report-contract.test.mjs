import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const reviewsStore = read('../src/stores/reviews.ts')
const workspaceStore = read('../src/stores/workspace.ts')
const revisionHistory = read('../src/components/manuscript/RevisionHistory.vue')
const types = read('../src/types/analysis.ts')

test('store exposes an idempotent consistency report action scoped to the active project', () => {
  // The action lives in the reviews domain store.
  assert.match(reviewsStore, /async function runConsistencyCheck\(revisionId: string, force = false\)/)
  assert.match(
    reviewsStore,
    /\/projects\/\$\{projectId\}\/analysis\/consistency\/from-revision\/\$\{revisionId\}/,
  )
  // Results are dropped when the user switches projects mid-request.
  assert.match(
    reviewsStore,
    /const report: ConsistencyReport = await response\.json\(\)\r?\n\s+if \(!isActiveProject\(projectId\)\)/,
  )
  // ...and the workspace switch resets every domain store, clearing any
  // finished report with them.
  assert.match(workspaceStore, /resetProjectState\(\)/)
  assert.match(reviewsStore, /consistencyReport\.value = null/)
})

test('revision history renders evidence-backed findings with severity and rule metadata', () => {
  assert.match(revisionHistory, /@click="runConsistencyCheck\(revision\.id\)"/)
  assert.match(revisionHistory, /class="consistency-report"/)
  assert.match(revisionHistory, /finding\.manuscript_excerpt/)
  assert.match(revisionHistory, /finding\.expected_value/)
  assert.match(revisionHistory, /finding\.observed_value/)
  assert.match(revisionHistory, /finding\.suggested_action/)
  assert.match(revisionHistory, /finding\.rule_code/)
})

test('consistency report types mirror the backend contract', () => {
  assert.match(types, /export type ConsistencyFinding = \{/)
  assert.match(types, /manuscript_source_ref: string/)
  assert.match(types, /confidence: 'exact' \| 'heuristic'/)
  assert.match(types, /export type ConsistencyReportSummary = \{/)
  assert.match(types, /critical_count: number/)
})
