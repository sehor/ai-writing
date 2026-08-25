import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const workspaceStore = read('../src/stores/workspace.ts')
const snowflakeStore = read('../src/stores/snowflake.ts')
const canonStore = read('../src/stores/canon.ts')
const manuscriptStore = read('../src/stores/manuscript.ts')
const memoryStore = read('../src/stores/memory.ts')
const draftCache = read('../src/services/draftCache.ts')
const draftSessions = read('../src/services/draftSessions.ts')
const editorSession = read('../src/stores/editorSession.ts')
const dirtyGuard = read('../src/composables/useDirtyGuard.ts')
const scopedRequest = read('../src/composables/useScopedRequest.ts')

test('draft cache persists snapshots per scope key and never throws', () => {
  assert.match(draftCache, /const STORAGE_PREFIX = 'ai-writing:draft:v1:'/)
  assert.match(draftCache, /export function saveDraft<T>/)
  assert.match(draftCache, /export function loadDraft<T>/)
  assert.match(draftCache, /export function clearDraft\(scopeKey: string\)/)
  // Every storage access is wrapped so quota/private-mode failures stay quiet.
  const tryBlocks = draftCache.match(/try \{/g) ?? []
  assert.ok(tryBlocks.length >= 3, 'save/load/clear must guard localStorage access')
})

test('editor session tracks the unified draft state shape', () => {
  const stateShape = read(
    '../src/stores/editorSession.ts',
  )
  assert.match(stateShape, /interface EditorDraftState \{[\s\S]*?scopeKey: string[\s\S]*?dirty: boolean[\s\S]*?lastSavedAt\?: string[\s\S]*?lastAutosavedAt\?: string/)
  assert.match(editorSession, /function markDirty\(scopeKey: string/)
  assert.match(editorSession, /function markClean\(scopeKey: string/)
  assert.match(editorSession, /function dirtyScopeKeys\(\): string\[\]/)
})

// Selection guards now live next to the domain state they protect.
const guardedWatchers = [
  ['watch(activeProjectId', workspaceStore],
  ['watch(activeStepNumber', workspaceStore],
  ['watch(activeCanonId', canonStore],
  ['watch(activeChapterId', manuscriptStore],
  ['watch(activeSceneId', manuscriptStore],
  ['watch(activeMemoryId', memoryStore],
]

test('domain stores guard every editable scope before switching away', () => {
  for (const [watcher, source] of guardedWatchers) {
    const start = source.indexOf(watcher)
    assert.notEqual(start, -1, watcher + ') must exist')
    const section = source.slice(start, start + 6000)
    assert.match(section, /isScopeDirty\(/, watcher + ' checks dirty state')
    assert.match(
      section,
      /confirmLeave(Multiple)?\(/,
      watcher + ' asks before leaving',
    )
    assert.match(section, /persistDraft\(/, watcher + ' autosaves on leave')
    assert.match(
      section,
      /suppressNextSelectionGuard = true\s*\n\s*(active\w+\.value = prev|return)/,
      watcher + ' can cancel the switch',
    )
  }
})

test('entering a scope restores cached drafts and saves clear the cache', () => {
  // The project-switch orchestration in the workspace store restores every
  // domain editor when the incoming project's data arrives.
  assert.match(workspaceStore, /restoreEntryDraft</)
  assert.match(workspaceStore, /restoreCachedDraft<string>\(/)
  assert.match(workspaceStore, /已恢复本地草稿/)
  assert.match(draftSessions, /已恢复本地草稿/)
  // Successful saves drop the local safety net and re-baseline.
  assert.match(snowflakeStore, /discardSavedScope\(artifactScopeKey\(projectId, saved\.step_number\)/)
  const clearAfterSave = [
    ['clearDraft(canonScopeKey(projectId, activeCanonId.value))', canonStore],
    ['clearDraft(chapterScopeKey(projectId, activeChapterId.value))', manuscriptStore],
    ['clearDraft(sceneScopeKey(projectId, activeSceneId.value))', manuscriptStore],
    ['clearDraft(memoryScopeKey(projectId, activeMemoryId.value))', memoryStore],
    ['clearDraft(manuscriptEditScopeKey(projectId, sceneId))', manuscriptStore],
  ]
  for (const [snippet, source] of clearAfterSave) {
    assert.ok(source.includes(snippet), 'missing save cleanup: ' + snippet)
  }
})

test('page close flushes dirty drafts and warns before unload', () => {
  assert.match(dirtyGuard, /addEventListener\('beforeunload'/)
  assert.match(dirtyGuard, /options\.flushAll\(\)/)
  assert.match(dirtyGuard, /event\.preventDefault\(\)/)
  assert.match(
    workspaceStore,
    /useDirtyGuard\(\{\s*flushAll: flushAllDirtyDrafts,?\s*\}\)/,
  )
  assert.match(workspaceStore, /function flushAllDirtyDrafts\(\): void/)
})

test('snowflake generation responses are bound to project and step scopes', () => {
  assert.match(scopedRequest, /export interface RequestScope \{/) 
  assert.match(scopedRequest, /projectId: string/)
  assert.match(scopedRequest, /domain: string/)
  assert.match(scopedRequest, /entityId: string/)
  assert.match(scopedRequest, /requestId: number/)

  const generateStart = snowflakeStore.indexOf('async function generateArtifact')
  const generateEnd = snowflakeStore.indexOf('\n  async function ', generateStart + 1)
  const generateSource = snowflakeStore.slice(
    generateStart,
    generateEnd === -1 ? undefined : generateEnd
  )
  assert.match(generateSource, /requestScopes\.begin\(\s*projectId,\s*'snowflake',\s*String\(ws\(\)\.activeStepNumber\)\s*\)/)
  const currentChecks = generateSource.match(/requestScopes\.isCurrent\(generationScope\)/g) ?? []
  assert.ok(currentChecks.length >= 2, 'success and error paths must both validate the scope')
})
