import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const workspaceStore = readFileSync(
  new URL('../src/stores/workspace.ts', import.meta.url),
  'utf8',
)

test('workspace status and proposal refresh logic use narrow safe patterns', () => {
  assert.match(workspaceStore, /type ApiStatus = 'checking' \| 'ok' \| 'offline'/)
  assert.match(workspaceStore, /const apiStatus = ref<ApiStatus>\('checking'\)/)
  assert.match(workspaceStore, /return value\.split\('_'\)\.join\(' '\)/)
  assert.match(
    workspaceStore,
    /await Promise\.all\(\[\s*loadManuscriptScenes\(projectId\),\s*loadManuscriptRevisions\(projectId\),\s*loadWritebackProposals\(projectId\),?\s*\]\)/s,
  )
})
