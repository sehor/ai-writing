import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { useManuscriptStore } from '../src/stores/manuscript'
import { loadDraft, saveDraft } from '../src/services/draftCache'
import AcceptedManuscript from '../src/components/manuscript/AcceptedManuscript.vue'
import type { ManuscriptScene } from '../src/types'

const { workspace } = vi.hoisted(() => ({ workspace: { activeProjectId: 'a', activeProject: { id: 'a' } } }))
vi.mock('../src/stores/workspace', () => ({ useWorkspaceStore: () => workspace }))
vi.mock('../src/stores/reviews', () => ({ useReviewsStore: () => ({
  loadWritebackProposals: vi.fn(), loadPostAcceptAnalysisJobs: vi.fn(), showLatestConsistencyReport: vi.fn(),
}) }))
vi.mock('../src/stores/graph', () => ({ useGraphStore: () => ({}) }))

const key = 'manuscript:a:scene'
const original = { id: 'accepted', project_id: 'a', scene_id: 'scene', proposal_id: 'proposal', title: 'Opening', content: 'Original', version: 1, accepted_at: 'now' } satisfies ManuscriptScene
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
let request = vi.fn<typeof fetch>()

function open(scene = original) {
  const store = useManuscriptStore()
  store.manuscriptScenes = [scene]
  store.startEditingManuscriptScene(scene)
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  workspace.activeProjectId = 'a'; workspace.activeProject = { id: 'a' }
  request = vi.fn<typeof fetch>()
  vi.stubGlobal('fetch', request)
  vi.stubGlobal('confirm', vi.fn(() => true))
  vi.useFakeTimers()
})
afterEach(async () => {
  useManuscriptStore().resetProjectState()
  await vi.runAllTimersAsync()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('successful save sends the editing version and clears the cache without delayed resurrection', async () => {
  const store = open()
  store.manuscriptEditContent = 'Author edit'
  const updated = { ...original, content: 'Author edit', version: 2 }
  request.mockImplementation(async (url, init) => json(init?.method === 'PUT' ? updated : String(url).endsWith('/scenes') ? [updated] : []))
  await store.saveManuscriptSceneEdit('scene')
  expect(JSON.parse(request.mock.calls[0]![1]!.body as string)).toEqual({ title: 'Opening', content: 'Author edit', expected_scene_version: 1 })
  expect(store.editingManuscriptSceneId).toBe('')
  await vi.runAllTimersAsync()
  expect(loadDraft(key)).toBeNull()
})

test('restored cached edits retain their old version and block save after official text changes', async () => {
  let store = open()
  store.manuscriptEditContent = 'Cached edit'
  await vi.advanceTimersByTimeAsync(400)
  expect(loadDraft(key)?.value).toMatchObject({ expected_scene_version: 1 })
  store.resetProjectState()
  store = open({ ...original, version: 2, content: 'Other window' })
  expect(store.manuscriptEditContent).toBe('Cached edit')
  expect(store.manuscriptEditVersion).toBe(1)
  expect(store.manuscriptEditNeedsReview).toBe(true)
  await store.saveManuscriptSceneEdit('scene')
  expect(request).not.toHaveBeenCalled()
})

test('legacy unversioned drafts keep their prose but require explicit review', async () => {
  saveDraft(key, { title: 'Legacy', content: 'Do not discard' })
  const store = open()
  expect(store.manuscriptEditVersion).toBeNull()
  expect(store.manuscriptEditContent).toBe('Do not discard')
  await store.saveManuscriptSceneEdit('scene')
  expect(request).not.toHaveBeenCalled()
  store.rebaseManuscriptSceneEdit()
  expect(store.manuscriptEditVersion).toBe(1)
  expect(loadDraft(key)?.value).toMatchObject({ content: 'Do not discard', expected_scene_version: 1 })
})

test('409 shows current text, preserves edits and requires acknowledgment before retry', async () => {
  const store = open()
  store.manuscriptEditContent = 'My edit'
  const current = { ...original, content: 'Other window edit', version: 2 }
  request.mockResolvedValueOnce(json({ detail: 'Version changed' }, 409)).mockResolvedValueOnce(json([current]))
  const wrapper = mount(AcceptedManuscript)
  try {
    await store.saveManuscriptSceneEdit('scene')
    await nextTick()
    expect(wrapper.get('textarea').element.value).toBe('My edit')
    expect(wrapper.get('[aria-label="正文版本冲突"]').text()).toContain('Other window edit')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(loadDraft(key)?.value).toMatchObject({ content: 'My edit', expected_scene_version: 1 })
    const acknowledge = wrapper.findAll('button').find(button => button.text().includes('已核对'))!
    await acknowledge.trigger('click')
    expect(store.manuscriptEditNeedsReview).toBe(false)
    expect(request).toHaveBeenCalledTimes(2) // Acknowledgment must not save.
    const updated = { ...current, content: 'My edit', version: 3 }
    request.mockImplementation(async (url, init) => json(init?.method === 'PUT' ? updated : String(url).endsWith('/scenes') ? [updated] : []))
    await store.saveManuscriptSceneEdit('scene')
    expect(JSON.parse(request.mock.calls[2]![1]!.body as string).expected_scene_version).toBe(2)
    expect(store.editingManuscriptSceneId).toBe('')
  } finally { wrapper.unmount() }
})

test('failed conflict refresh cannot acknowledge stale displayed text and remains retryable', async () => {
  const store = open()
  store.manuscriptEditContent = 'Keep me'
  request.mockResolvedValueOnce(json({}, 409)).mockRejectedValueOnce(new Error('Offline'))
  await store.saveManuscriptSceneEdit('scene')
  store.rebaseManuscriptSceneEdit()
  expect(store.manuscriptEditNeedsReview).toBe(true)
  expect(store.manuscriptEditReviewReady).toBe(false)
  expect(store.manuscriptError).toContain('读取当前正文失败')
  request.mockResolvedValueOnce(json([{ ...original, version: 2 }]))
  await store.refreshManuscriptEditConflict()
  store.rebaseManuscriptSceneEdit()
  expect(store.manuscriptEditVersion).toBe(2)
  expect(store.manuscriptEditContent).toBe('Keep me')
})

test('scene switches capture each autosave snapshot including its own base version', async () => {
  const store = open()
  store.manuscriptEditContent = 'Scene one'
  store.startEditingManuscriptScene({ ...original, id: 'accepted-2', scene_id: 'second', version: 4 })
  store.manuscriptEditContent = 'Scene two'
  await vi.advanceTimersByTimeAsync(400)
  expect(loadDraft(key)?.value).toMatchObject({ content: 'Scene one', expected_scene_version: 1 })
  expect(loadDraft('manuscript:a:second')?.value).toMatchObject({ content: 'Scene two', expected_scene_version: 4 })
})

test.each([200, 409, 500])('late save response %s cannot clear a reopened editor or its cache', async status => {
  let resolve!: (response: Response) => void
  request.mockReturnValueOnce(new Promise<Response>(done => { resolve = done }))
  const store = open()
  store.manuscriptEditContent = 'Old request'
  const pending = store.saveManuscriptSceneEdit('scene')
  store.resetProjectState()
  workspace.activeProjectId = 'b'; workspace.activeProject = { id: 'b' }
  store.resetProjectState()
  workspace.activeProjectId = 'a'; workspace.activeProject = { id: 'a' }
  open()
  store.manuscriptEditContent = 'New unsaved edit'
  resolve(json({ ...original, version: 2 }, status))
  await pending
  await vi.runAllTimersAsync()
  expect(store.editingManuscriptSceneId).toBe('scene')
  expect(store.manuscriptEditContent).toBe('New unsaved edit')
  expect(store.manuscriptError).toBe('')
  expect(loadDraft(key)?.value).toMatchObject({ content: 'New unsaved edit', expected_scene_version: 1 })
})

test('duplicate submits are ignored and input changed in flight is retained', async () => {
  let resolve!: (response: Response) => void
  const updated = { ...original, content: 'Submitted', version: 2 }
  request.mockImplementation(async url => json(String(url).endsWith('/scenes') ? [updated] : []))
  request.mockImplementationOnce(() => new Promise<Response>(done => { resolve = done }))
  const store = open()
  store.manuscriptEditContent = 'Submitted'
  const pending = store.saveManuscriptSceneEdit('scene')
  await store.saveManuscriptSceneEdit('scene')
  expect(request).toHaveBeenCalledTimes(1)
  store.manuscriptEditContent = 'Later input'
  resolve(json(updated))
  await pending
  expect(store.editingManuscriptSceneId).toBe('scene')
  expect(store.manuscriptEditContent).toBe('Later input')
  expect(loadDraft(key)?.value).toMatchObject({ content: 'Later input', expected_scene_version: 2 })
})
