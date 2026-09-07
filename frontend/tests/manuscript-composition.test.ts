import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia, storeToRefs } from 'pinia'
import { fetchApi } from '../src/api/client'
import { useProjectContextStore } from '../src/stores/projectContext'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useProposalDraftStore } from '../src/stores/proposalDraft'
import type { ManuscriptProposal, ManuscriptScene } from '../src/types'

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
let pinia = createPinia()
const scene = { id: 'accepted', project_id: 'a', scene_id: 'scene', proposal_id: 'proposal', title: 'Opening', content: 'Original', version: 1, accepted_at: 'now' } satisfies ManuscriptScene

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  useProjectContextStore().activeProjectId = 'a'
  localStorage.clear()
  vi.mocked(fetchApi).mockReset()
  vi.useFakeTimers()
})
afterEach(() => {
  vi.runAllTimers()
  disposePinia(pinia)
  vi.useRealTimers()
})

test.each(['accept', 'save', 'restore'] as const)('%s refreshes content, revisions and the configured review panels once', async action => {
  const store = useManuscriptStore()
  const refs = storeToRefs(store)
  const port = {
    loadWritebackProposals: vi.fn(async () => {}),
    loadPostAcceptAnalysisJobs: vi.fn(async () => {}),
    showLatestConsistencyReport: vi.fn(async () => {}),
  }
  store.configureReviewPort(port)
  store.manuscriptScenes = [scene]
  const proposal = { id: 'proposal', title: 'Opening', content: 'Proposed', status: 'pending_review' } as ManuscriptProposal
  store.manuscriptProposals = [proposal]
  const updated = { ...scene, version: 2, content: 'Committed' }
  vi.mocked(fetchApi).mockImplementation(async (url, options) => {
    if (options?.method === 'POST') return Response.json({ ...proposal, status: 'accepted' })
    if (options?.method === 'PUT') return Response.json(updated)
    return Response.json(url.endsWith('/scenes') ? [updated] : [{ id: 'revision', title: 'Opening', version: 2 }])
  })
  if (action === 'accept') {
    useProposalDraftStore().open('a', proposal, 1)
    await store.updateProposalStatus('proposal', 'accepted')
  } else if (action === 'save') {
    store.startEditingManuscriptScene(scene)
    refs.manuscriptEditContent.value = 'Committed'
    await store.saveManuscriptSceneEdit('scene')
    expect(refs.manuscriptEditVersion.value).toBe(2)
  } else {
    await store.restoreRevision('old-revision')
  }
  expect(store.manuscriptError).toBe('')
  expect(refs.manuscriptScenes.value).toEqual([updated])
  expect(store.revisionCount).toBe(1)
  expect(store.diffRightRevisionId).toBe('revision')
  for (const callback of Object.values(port)) {
    expect(callback).toHaveBeenCalledExactlyOnceWith('a')
  }
  const reads = vi.mocked(fetchApi).mock.calls.filter(([, options]) => !options?.method).map(([url]) => url)
  expect(reads).toEqual(['/projects/a/manuscript/scenes', '/projects/a/manuscript/revisions'])
})

test('late proposal generation cannot populate the next project', async () => {
  const store = useManuscriptStore()
  store.activeSceneId = 'scene'
  let finish!: (response: Response) => void
  vi.mocked(fetchApi).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const pending = store.createProposalFromScene()
  useProjectContextStore().activeProjectId = 'b'
  store.resetProjectState()
  finish(Response.json({ id: 'old-proposal' }))
  await pending
  expect(store.manuscriptProposals).toEqual([])
  expect(store.activeProposalId).toBe('')
})

test('history operations preserve the current edit and project reset clears each owned surface', async () => {
  const store = useManuscriptStore()
  store.manuscriptScenes = [scene]
  store.startEditingManuscriptScene(scene)
  store.manuscriptEditContent = 'Unsaved author text'
  store.diffLeftRevisionId = 'left'
  store.diffRightRevisionId = 'right'
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json({ summary: 'diff' }))
    .mockResolvedValueOnce(Response.json({ content: 'export' }))
  await store.loadRevisionDiff()
  await store.exportManuscript()
  expect(store.revisionDiff).toEqual({ summary: 'diff' })
  expect(store.manuscriptExport).toEqual({ content: 'export' })
  expect(store.currentManuscriptEdits()).toEqual({ title: 'Opening', content: 'Unsaved author text', expected_scene_version: 1 })
  expect(store.draftSnapshotEntries().map(([key]) => key)).toEqual(['chapter:a:new', 'scene:a:new', 'manuscript:a:scene'])
  store.resetProjectState()
  expect(store.manuscriptScenes).toEqual([])
  expect(store.editingManuscriptSceneId).toBe('')
  expect(store.manuscriptEditContent).toBe('')
  expect(store.revisionDiff).toBeNull()
  expect(store.manuscriptExport).toBeNull()
  expect(store.diffRightRevisionId).toBe('')
})
