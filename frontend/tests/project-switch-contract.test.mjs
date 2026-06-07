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
