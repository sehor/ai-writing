import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const workspaceStore = read('../src/stores/workspace.ts')
const draftCache = read('../src/services/draftCache.ts')
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

test('workspace guards every editable scope before switching away', () => {
  for (const watcher of [
    'watch(activeProjectId',
    'watch(activeStepNumber',
    'watch(activeCanonId',
    'watch(activeChapterId',
    'watch(activeSceneId',
    'watch(activeMemoryId',
  ]) {
    const start = workspaceStore.indexOf(watcher)
    assert.notEqual(start, -1, `${watcher}) must exist`)
    const section = workspaceStore.slice(start, start + 6000)
    assert.match(section, /isScopeDirty\(/, `${watcher} checks dirty state`)
    assert.match(
      section,
      /confirmLeave(Multiple)?\(/,
      `${watcher} asks before leaving`,
    )
    assert.match(section, /persistDraft\(/, `${watcher} autosaves on leave`)
    assert.match(
      section,
      /suppressNextSelectionGuard = true\s*\n\s*(active\w+\.value = prev|return)/,
      `${watcher} can cancel the switch`,
    )
  }
})

test('entering a scope restores cached drafts and saves clear the cache', () => {
  assert.match(workspaceStore, /restoreEntryDraft</)
  assert.match(workspaceStore, /restoreCachedDraft<string>\(/)
  assert.match(workspaceStore, /已恢复本地草稿/)
  // Successful saves drop the local safety net and re-baseline.
  assert.match(workspaceStore, /discardSavedScope\(artifactScopeKey\(projectId, saved\.step_number\)/)
  for (const clear of [
    'clearDraft(canonScopeKey(projectId, activeCanonId.value))',
    'clearDraft(chapterScopeKey(projectId, activeChapterId.value))',
    'clearDraft(sceneScopeKey(projectId, activeSceneId.value))',
    'clearDraft(memoryScopeKey(projectId, activeMemoryId.value))',
    'clearDraft(manuscriptEditScopeKey(projectId, sceneId))',
  ]) {
    assert.ok(workspaceStore.includes(clear), `missing save cleanup: ${clear}`)
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

  const generateStart = workspaceStore.indexOf('async function generateArtifact')
  const generateEnd = workspaceStore.indexOf('\n  async function ', generateStart + 1)
  const generateSource = workspaceStore.slice(
    generateStart,
    generateEnd === -1 ? undefined : generateEnd
  )
  assert.match(generateSource, /requestScopes\.begin\(\s*projectId,\s*'snowflake',\s*String\(activeStepNumber\.value\)\s*\)/)
  const currentChecks = generateSource.match(/requestScopes\.isCurrent\(generationScope\)/g) ?? []
  assert.ok(currentChecks.length >= 2, 'success and error paths must both validate the scope')
})
