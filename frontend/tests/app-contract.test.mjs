import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const types = readFileSync(new URL('../src/types/index.ts', import.meta.url), 'utf8')
const workspaceStore = readFileSync(
  new URL('../src/stores/workspace.ts', import.meta.url),
  'utf8',
)
const referenceWorkspace = readFileSync(
  new URL('../src/components/manuscript/ReferenceWorkspace.vue', import.meta.url),
  'utf8',
)

test('structured references UI uses reviewable suggestion endpoints', () => {
  assert.match(types, /export type ReferenceSuggestion\b/)
  assert.match(workspaceStore, /referenceSuggestions\s*=\s*ref<ReferenceSuggestion\[\]>/)
  assert.match(workspaceStore, /\/api\/projects\/\$\{projectId\}\/references\/suggestions/)
  assert.match(
    workspaceStore,
    /\/api\/projects\/\$\{projectId\}\/references\/suggestions\/generate/,
  )
  assert.match(
    workspaceStore,
    /\/api\/projects\/\$\{projectId\}\/references\/suggestions\/\$\{suggestionId\}\/status/,
  )
  assert.match(referenceWorkspace, /Reference Suggestions/)
  assert.match(referenceWorkspace, /Generate Reference/)
  assert.match(referenceWorkspace, /Accept Reference/)
  assert.doesNotMatch(referenceWorkspace, /chat\s*box/i)
})
