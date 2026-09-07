import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const workspaceStore = read('../src/stores/workspace.ts')

test('project switching cancels stale project data requests', () => {
  assert.match(workspaceStore, /let projectLoadController: AbortController \| null/)
  assert.match(workspaceStore, /projectLoadController\?\.abort\(\)/)
  assert.match(workspaceStore, /const controller = new AbortController\(\)/)
  assert.match(workspaceStore, /projectLoadController = controller/)
  assert.match(workspaceStore, /signal:\s*controller\.signal/)
  assert.match(workspaceStore, /if \(controller\.signal\.aborted\) \{\s*return\s*\}/s)
  assert.match(workspaceStore, /error instanceof DOMException && error\.name === 'AbortError'/)
})

test('the workspace store owns the active-project staleness check', () => {
  assert.match(
    workspaceStore,
    /function isActiveProject\(projectId: string\) \{\s*return projectId === activeProjectId\.value\s*\}/s,
  )
})

// Project-scoped mutations now live in their domain stores; each one must
// still ignore responses that arrive after the active project changed.
const staleGuardedFunctions = [
  ['saveCanonEntity', '../src/stores/canon.ts'],
  // Manuscript mutation isolation is covered by executable session/composition tests.
  ['generateReferenceSuggestion', '../src/stores/reviews.ts'],
  // Manual saves use an editor-session guard as well as project identity.
  // Their late-response behavior is covered by manuscript-conflicts.test.ts.
  ['createWritebackFromRevision', '../src/stores/reviews.ts'],
  ['saveMemoryRecord', '../src/stores/memory.ts'],
]

test('project-scoped mutations ignore responses after the active project changes', () => {
  for (const [functionName, file] of staleGuardedFunctions) {
    const source = read(file)
    const start = source.indexOf('async function ' + functionName)
    const end = source.indexOf('\n  async function ', start + 1)
    const functionSource = source.slice(start, end === -1 ? undefined : end)

    assert.notEqual(start, -1, functionName + ' must exist in ' + file)
    assert.match(
      functionSource,
      /if \(!isActiveProject\(projectId\)\) \{\s*return\s*\}/s,
      functionName + ' (' + file + ') must ignore stale project responses',
    )
  }
})
