import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useCanonStore } from '../src/stores/canon'
import { useMemoryStore } from '../src/stores/memory'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useEditorSessionStore } from '../src/stores/editorSession'
import { loadDraft } from '../src/services/draftCache'
import { isScopeDirty, persistDraft, queueAutosave, setBaseline } from '../src/services/draftSessions'

vi.mock('../src/stores/workspace', () => ({
  useWorkspaceStore: () => ({ activeProjectId: 'autosave', activeProject: { id: 'autosave' } }),
}))

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.useFakeTimers()
  vi.stubGlobal('confirm', vi.fn(() => true))
})
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

for (const delay of [0, 500]) {
  test(`Canon A → B → A retains author edits after ${delay}ms`, async () => {
    const store = useCanonStore()
    store.canonEntities = ['a', 'b'].map((id) => ({
      ...store.createEmptyCanonDraft(), id, project_id: 'autosave', name: id, version: 1,
    }))
    store.activeCanonId = 'a'
    await nextTick()
    store.canonDraft.summary = 'author A'
    await nextTick()
    vi.advanceTimersByTime(delay)
    store.activeCanonId = 'b'
    await nextTick()
    vi.advanceTimersByTime(500)
    expect(loadDraft<{ summary: string }>('canon:autosave:a')?.value.summary).toBe('author A')
    expect(store.canonDraft.summary).toBe('')
    expect(loadDraft('canon:autosave:b')).toBeNull()
    store.activeCanonId = 'a'
    await nextTick()
    expect(store.canonDraft.summary).toBe('author A')
  })
}

test('Memory, Chapter and Scene switches preserve their independent snapshots', async () => {
  const memory = useMemoryStore()
  const manuscript = useManuscriptStore()
  memory.memoryRecords = ['a', 'b'].map((id) => ({
    ...memory.createEmptyMemoryDraft(), id, project_id: 'autosave', title: id,
  }))
  manuscript.manuscriptChapters = ['a', 'b'].map((id) => ({
    id, project_id: 'autosave', sequence: 1, title: id, summary: '',
  }))
  manuscript.sceneContracts = ['a', 'b'].map((id) => ({
    ...manuscript.createEmptySceneDraft(), id, project_id: 'autosave', title: id,
  }))
  memory.activeMemoryId = manuscript.activeChapterId = manuscript.activeSceneId = 'a'
  await nextTick()
  memory.memoryDraft.content = 'memory A'
  manuscript.chapterDraft.summary = 'chapter A'
  manuscript.sceneDraft.outcome = 'scene A'
  await nextTick()
  memory.activeMemoryId = manuscript.activeChapterId = manuscript.activeSceneId = 'b'
  await nextTick()
  vi.advanceTimersByTime(500)
  expect(loadDraft<{ content: string }>('memory:autosave:a')?.value.content).toBe('memory A')
  expect(loadDraft<{ summary: string }>('chapter:autosave:a')?.value.summary).toBe('chapter A')
  expect(loadDraft<{ outcome: string }>('scene:autosave:a')?.value.outcome).toBe('scene A')
})

test('flush on project change or page close cancels a stale queued snapshot', () => {
  const key = 'canon:flush:a'
  setBaseline(key, { summary: '' })
  const shared = { summary: 'queued' }
  queueAutosave(key, () => shared)
  shared.summary = 'latest edit before leaving'
  persistDraft(key, shared)
  shared.summary = 'other project'
  vi.advanceTimersByTime(500)
  expect(loadDraft(key)?.value).toEqual({ summary: 'latest edit before leaving' })
})

test('disposing a store cannot make a pending timer read another editor', async () => {
  const store = useCanonStore()
  setBaseline(store.canonScopeKey(), store.canonDraft)
  store.canonDraft.summary = 'before unmount'
  await nextTick()
  store.$dispose()
  store.canonDraft.summary = 'after unmount'
  vi.advanceTimersByTime(500)
  expect(loadDraft<{ summary: string }>(store.canonScopeKey())?.value.summary).toBe('before unmount')
})

test('cache failure preserves dirty state and immediate leave protection', async () => {
  const store = useCanonStore()
  setBaseline(store.canonScopeKey(), store.canonDraft)
  vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => { throw new Error('quota') })
  store.canonDraft.summary = 'keep me'
  await nextTick()
  expect(useEditorSessionStore().isDirty(store.canonScopeKey())).toBe(true)
  vi.advanceTimersByTime(500)
  expect(useEditorSessionStore().draftState(store.canonScopeKey())?.autosaveFailed).toBe(true)
  expect(isScopeDirty(store.canonScopeKey(), store.canonDraft)).toBe(true)
})
