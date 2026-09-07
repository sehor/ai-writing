import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick, reactive } from 'vue'
import { useCanonStore } from '../src/stores/canon'
import { useMemoryStore } from '../src/stores/memory'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useEditorSessionStore } from '../src/stores/editorSession'
import { loadDraft, saveDraft } from '../src/services/draftCache'
import { isScopeDirty, setBaseline } from '../src/services/draftSessions'

const shell = reactive({ activeProjectId: 'save', activeProject: { id: 'save' } })
vi.mock('../src/stores/workspace', () => ({ useWorkspaceStore: () => shell }))
vi.mock('../src/stores/graph', () => ({ useGraphStore: () => ({ loadGraphAnalysis: vi.fn() }) }))

beforeEach(() => {
  setActivePinia(createPinia())
  shell.activeProjectId = shell.activeProject.id = 'save'
  localStorage.clear()
  vi.useFakeTimers()
  vi.stubGlobal('confirm', vi.fn(() => true))
})
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function editor(domain: string) {
  if (domain === 'canon') {
    const s = useCanonStore()
    s.canonEntities = ['a', 'b'].map((id) => ({ ...s.createEmptyCanonDraft(), id, project_id: 'save', name: id, version: 1 }))
    return { select: (id: string) => { s.activeCanonId = id }, selected: () => s.activeCanonId,
      edit: (text: string) => { s.canonDraft.name = text }, read: () => s.canonDraft.name,
      draft: () => ({ ...s.canonDraft }), scope: () => s.canonScopeKey(), save: s.saveCanonEntity }
  }
  if (domain === 'memory') {
    const s = useMemoryStore()
    s.memoryRecords = ['a', 'b'].map((id) => ({ ...s.createEmptyMemoryDraft(), id, project_id: 'save', title: id, content: 'content' }))
    return { select: (id: string) => { s.activeMemoryId = id }, selected: () => s.activeMemoryId,
      edit: (text: string) => { s.memoryDraft.title = text; s.memoryDraft.content = 'content' }, read: () => s.memoryDraft.title,
      draft: () => ({ ...s.memoryDraft }), scope: () => s.memoryScopeKey(), save: s.saveMemoryRecord }
  }
  const s = useManuscriptStore()
  if (domain === 'chapter') {
    s.manuscriptChapters = ['a', 'b'].map((id) => ({ ...s.createEmptyChapterDraft(), id, project_id: 'save', title: id }))
    return { select: (id: string) => { s.activeChapterId = id }, selected: () => s.activeChapterId,
      edit: (text: string) => { s.chapterDraft.title = text }, read: () => s.chapterDraft.title,
      draft: () => ({ ...s.chapterDraft }), scope: () => s.chapterScopeKey(), save: s.saveChapter }
  }
  s.sceneContracts = ['a', 'b'].map((id) => ({ ...s.createEmptySceneDraft(), id, project_id: 'save', title: id }))
  return { select: (id: string) => { s.activeSceneId = id }, selected: () => s.activeSceneId,
    edit: (text: string) => { s.sceneDraft.title = text }, read: () => s.sceneDraft.title,
    draft: () => ({ ...s.sceneDraft }), scope: () => s.sceneScopeKey(), save: s.saveSceneContract }
}

function deferredSave() {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve })))
  return (value: unknown, status = 200) => finish(new Response(JSON.stringify(value), { status }))
}

for (const domain of ['canon', 'memory', 'chapter', 'scene']) {
  test(`${domain}: saved baseline becomes clean and the next denied switch stays put`, async () => {
    const e = editor(domain)
    e.select('a')
    e.edit('saved')
    await nextTick()
    const finish = deferredSave()
    const pending = e.save()
    finish({ ...e.draft(), id: 'a', project_id: 'save' })
    await pending
    await nextTick()
    expect(isScopeDirty(e.scope(), e.draft())).toBe(false)
    expect(useEditorSessionStore().isDirty(e.scope())).toBe(false)
    e.edit('unsaved again')
    vi.mocked(window.confirm).mockReturnValue(false)
    e.select('b')
    await nextTick()
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(e.selected()).toBe('a')
    expect(e.read()).toBe('unsaved again')
  })

  for (const recordId of ['a', '']) {
    test(`${domain}: saving ${recordId || 'new'} preserves typing during the request`, async () => {
      const e = editor(domain)
      e.select(recordId)
      setBaseline(e.scope(), e.draft())
      e.edit('request snapshot')
      await nextTick()
      const finish = deferredSave()
      const sent = e.draft()
      const pending = e.save()
      e.edit('later typing')
      await nextTick()
      finish({ ...sent, id: recordId || 'created', project_id: 'save' })
      await pending
      await nextTick()
      expect(e.selected()).toBe(recordId || 'created')
      expect(e.read()).toBe('later typing')
      expect(isScopeDirty(e.scope(), e.draft())).toBe(true)
      expect(loadDraft(e.scope())?.value).toEqual(e.draft())
      e.edit('request snapshot')
      expect(isScopeDirty(e.scope(), e.draft())).toBe(false)
    })
  }

  test(`${domain}: late success cannot change another selection or clear its cache`, async () => {
    const e = editor(domain)
    e.select('a')
    e.edit('request snapshot')
    await nextTick()
    const finish = deferredSave()
    const sent = e.draft()
    const pending = e.save()
    e.select('b')
    e.edit('B draft')
    await nextTick()
    saveDraft(e.scope(), e.draft())
    finish({ ...sent, id: 'a', project_id: 'save' })
    await pending
    expect(e.selected()).toBe('b')
    expect(e.read()).toBe('B draft')
    expect(loadDraft(e.scope())?.value).toEqual(e.draft())
  })

  test(`${domain}: failure preserves draft; project round trip invalidates the response`, async () => {
    const e = editor(domain)
    e.select('a')
    e.edit('request snapshot')
    await nextTick()
    let finish = deferredSave()
    let pending = e.save()
    finish({}, 500)
    await pending
    expect(isScopeDirty(e.scope(), e.draft())).toBe(true)
    finish = deferredSave()
    pending = e.save()
    shell.activeProjectId = shell.activeProject.id = 'other'
    shell.activeProjectId = shell.activeProject.id = 'save'
    e.edit('after project reload')
    finish({ ...e.draft(), id: 'a', project_id: 'save' })
    await pending
    expect(e.read()).toBe('after project reload')
    expect(isScopeDirty(e.scope(), e.draft())).toBe(true)
  })
}
