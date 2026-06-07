import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const appVue = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('structured references UI uses reviewable suggestion endpoints', () => {
  assert.match(appVue, /type ReferenceSuggestion\b/)
  assert.match(appVue, /referenceSuggestions\s*=\s*ref<ReferenceSuggestion\[\]>/)
  assert.match(appVue, /\/api\/projects\/\$\{projectId\}\/references\/suggestions/)
  assert.match(appVue, /\/api\/projects\/\$\{projectId\}\/references\/suggestions\/generate/)
  assert.match(appVue, /\/api\/projects\/\$\{projectId\}\/references\/suggestions\/\$\{suggestionId\}\/status/)
  assert.match(appVue, /Reference Suggestions/)
  assert.match(appVue, /Generate Reference/)
  assert.match(appVue, /Accept Reference/)
  assert.doesNotMatch(appVue, /chat\s*box/i)
})
