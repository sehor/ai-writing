import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { useProposalDraftStore } from '../src/stores/proposalDraft'
import { useProjectContextStore } from '../src/stores/projectContext'
import { useManuscriptProposals } from '../src/stores/manuscript/proposals'
import { loadDraft } from '../src/services/draftCache'
import type { ManuscriptProposal } from '../src/types'

beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); useProjectContextStore().activeProjectId = 'p' })

test('late A acceptance cannot commit B or pull selection back after a forced editor reset', async () => {
  const draft = useProposalDraftStore()
  const proposal = (id: string) => ({ id, project_id: 'p', scene_id: id, title: id, content: 'original', status: 'pending_review' }) as ManuscriptProposal
  const a = proposal('a'), b = proposal('b')
  draft.open('p', b, 0); draft.content = 'B author text'; draft.persist()
  draft.open('p', a, 0)
  let finish!: (response: Response) => void
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const refresh = vi.fn(async () => {})
  const store = useManuscriptProposals({ manuscriptError: ref(''), manuscriptStatus: ref('') }, {
    activeSceneId: ref('a'), loadManuscriptScenes: async () => {}, refreshCommittedRevision: refresh,
  })
  store.manuscriptProposals.value = [a, b]; store.activeProposalId.value = 'a'
  const pending = store.updateProposalStatus('a', 'accepted')
  expect(draft.submitting).toBe(true)
  draft.open('p', b, 0); store.activeProposalId.value = 'b'
  finish(new Response(JSON.stringify({ ...a, status: 'accepted' }), { status: 200 }))
  await pending
  expect(draft.submitting).toBe(false)
  expect(store.activeProposalId.value).toBe('b')
  expect(refresh).not.toHaveBeenCalled()
  expect(loadDraft('proposal:p:b')?.value).toMatchObject({ content: 'B author text' })
  draft.open('p', a, 0); draft.open('p', b, 0)
  expect(draft.content).toBe('B author text')
})
