import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const workspaceStore = read('../src/stores/workspace.ts')
const formatUtils = read('../src/utils/format.ts')
const manuscriptStore = read('../src/stores/manuscript.ts')

test('workspace global status keeps narrow safe patterns', () => {
  assert.match(workspaceStore, /type ApiStatus = 'checking' \| 'ok' \| 'offline'/)
  assert.match(workspaceStore, /const apiStatus = ref<ApiStatus>\('checking'\)/)
})

test('shared label formatting humanizes enum values without unsafe parsing', () => {
  assert.match(formatUtils, /return value\.split\('_'\)\.join\(' '\)/)
})

test('proposal acceptance refreshes dependent collections in one batch', () => {
  assert.match(
    manuscriptStore,
    /await Promise\.all\(\[\s*loadManuscriptScenes\(projectId\),\s*loadManuscriptRevisions\(projectId\),\s*reviews\.loadWritebackProposals\(projectId\),?\s*\]\)/s,
  )
})
