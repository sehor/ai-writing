import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const workspaceStore = readFileSync(
  new URL('../src/stores/workspace.ts', import.meta.url),
  'utf8',
)

test('project switching cancels stale project data requests', () => {
  assert.match(workspaceStore, /let projectLoadController: AbortController \| null/)
  assert.match(workspaceStore, /projectLoadController\?\.abort\(\)/)
  assert.match(workspaceStore, /const controller = new AbortController\(\)/)
  assert.match(workspaceStore, /projectLoadController = controller/)
  assert.match(workspaceStore, /signal:\s*controller\.signal/)
  assert.match(workspaceStore, /if \(controller\.signal\.aborted\) \{\s*return\s*\}/s)
  assert.match(workspaceStore, /error instanceof DOMException && error\.name === 'AbortError'/)
})

test('project-scoped mutations ignore responses after the active project changes', () => {
  assert.match(
    workspaceStore,
    /function isActiveProject\(projectId: string\) \{\s*return projectId === activeProjectId\.value\s*\}/s,
  )

  for (const functionName of [
    'saveCanonEntity',
    'saveChapter',
    'saveSceneContract',
    'createProposalFromScene',
    'generateReferenceSuggestion',
    'saveManuscriptSceneEdit',
    'createWritebackFromRevision',
    'saveMemoryRecord',
  ]) {
    const start = workspaceStore.indexOf(`async function ${functionName}`)
    const end = workspaceStore.indexOf('\n  async function ', start + 1)
    const functionSource = workspaceStore.slice(start, end === -1 ? undefined : end)

    assert.notEqual(start, -1, `${functionName} must exist`)
    assert.match(
      functionSource,
      /if \(!isActiveProject\(projectId\)\) \{\s*return\s*\}/s,
      `${functionName} must ignore stale project responses`,
    )
  }
})
