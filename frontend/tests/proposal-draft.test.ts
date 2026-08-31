import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useProposalDraftStore } from '../src/stores/proposalDraft'
import { loadDraft } from '../src/services/draftCache'
import type { ManuscriptProposal } from '../src/types'

const proposal = { id: 'p', project_id: 'a', title: 'AI title', content: 'AI original', status: 'pending_review' } as ManuscriptProposal
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); vi.useFakeTimers() })
afterEach(() => { useProposalDraftStore().reset(); vi.useRealTimers() })

test('editing persists a separate draft without changing its AI source', async () => {
  const draft = useProposalDraftStore()
  draft.open('a', proposal, 2)
  draft.content = 'Author revision'
  await vi.advanceTimersByTimeAsync(400)
  expect(proposal.content).toBe('AI original')
  expect(loadDraft(draft.scopeKey)?.value).toEqual({ title: 'AI title', content: 'Author revision', expected_scene_version: 2 })
  draft.reset(); draft.open('a', proposal, 3)
  expect(draft.content).toBe('Author revision')
  expect(draft.expectedSceneVersion).toBe(2)
  expect(draft.dirty).toBe(true)
  draft.rebase(3)
  expect(draft.content).toBe('Author revision')
  expect(loadDraft(draft.scopeKey)?.value).toMatchObject({ expected_scene_version: 3 })
})

test('delayed autosave cannot cross project scopes, and successful commit clears it', async () => {
  const draft = useProposalDraftStore()
  draft.open('a', proposal, 0); draft.content = 'A draft'
  draft.open('b', { ...proposal, project_id: 'b' }, 0); draft.content = 'B draft'
  await vi.advanceTimersByTimeAsync(400)
  expect(loadDraft('proposal:a:p')?.value).toMatchObject({ content: 'A draft' })
  expect(loadDraft('proposal:b:p')?.value).toMatchObject({ content: 'B draft' })
  draft.committed()
  expect(draft.dirty).toBe(false)
  expect(loadDraft('proposal:b:p')).toBeNull()
})
