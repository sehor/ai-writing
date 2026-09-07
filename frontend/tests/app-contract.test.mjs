import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const types = readFileSync(new URL('../src/types/reference.ts', import.meta.url), 'utf8')
const reviewsStore = readFileSync(
  new URL('../src/stores/reviews.ts', import.meta.url),
  'utf8',
)
const referenceWorkspace = readFileSync(
  new URL('../src/components/manuscript/ReferenceWorkspace.vue', import.meta.url),
  'utf8',
)

test('structured references UI uses reviewable suggestion endpoints', () => {
  assert.match(types, /export type ReferenceSuggestion\b/)
  assert.match(reviewsStore, /referenceSuggestions\s*=\s*ref<ReferenceSuggestion\[\]>/)
  assert.match(reviewsStore, /\/projects\/\$\{projectId\}\/references\/suggestions/)
  assert.match(
    reviewsStore,
    /\/projects\/\$\{projectId\}\/references\/suggestions\/generate/,
  )
  assert.match(
    reviewsStore,
    /\/projects\/\$\{projectId\}\/references\/suggestions\/\$\{suggestionId\}\/status/,
  )
  assert.match(referenceWorkspace, /参考建议/)
  assert.match(referenceWorkspace, /生成参考建议/)
  assert.match(referenceWorkspace, /接受参考建议/)
  assert.doesNotMatch(referenceWorkspace, /chat\s*box/i)
})
