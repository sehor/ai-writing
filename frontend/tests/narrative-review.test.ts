import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import WritebackReview from '../src/components/manuscript/WritebackReview.vue'
import { useReviewsStore } from '../src/stores/reviews'
import { useNarrativeStore } from '../src/stores/narrative'
import { fetchApi } from '../src/api/client'
import type { StoryThread, WritebackProposal } from '../src/types'

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
vi.mock('../src/stores/workspace', () => ({ useWorkspaceStore: () => ({
  activeProjectId: 'novel', activeProject: { id: 'novel' }, activeStepNumber: 1,
}) }))

const proposal = (): WritebackProposal => ({
  id: 'proposal', project_id: 'novel', target: 'story_thread_status', action: 'update', title: 'Develop the door thread',
  rationale: 'Evidence', payload: { from_state: 'planted', proposed_state: 'developing', confidence: 0.9,
    evidence: [{ source_ref: 'manuscript_revision:r1', excerpt: 'Mira opened the door.' }] },
  source_ref: 'manuscript_revision:r1', target_record_id: 'thread', expected_version: null, changes: {},
  status: 'pending_review', created_at: '', reviewed_at: '', applied_record_id: '',
})
beforeEach(() => {
  setActivePinia(createPinia()); vi.mocked(fetchApi).mockReset()
  const reviews = useReviewsStore()
  reviews.writebackProposals = [proposal()]; reviews.activeWritebackId = 'proposal'
  useNarrativeStore().threads = [{ id: 'thread', title: 'Door', status: 'planted' } as StoryThread]
})

test('StoryThread acceptance uses lifecycle state, not a nonexistent Canon version', async () => {
  const wrapper = mount(WritebackReview)
  const accept = wrapper.findAll('button').find((button) => button.text() === '接受')!
  expect(accept.attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-testid="thread-status-proposal"]').text()).toContain('developing')
  expect(wrapper.text()).toContain('Mira opened the door.')
  const narrative = useNarrativeStore()
  const refresh = vi.spyOn(narrative, 'load').mockResolvedValue()
  vi.mocked(fetchApi).mockImplementation(async (path, options) => {
    if (options?.method === 'PUT') return Response.json({ ...proposal(), status: 'accepted' })
    return Response.json(path.includes('/writeback/') ? [{ ...proposal(), status: 'accepted' }] : [])
  })
  await useReviewsStore().updateWritebackStatus('proposal', 'accepted')
  expect(refresh).toHaveBeenCalledWith('novel')
  expect(useReviewsStore().writebackProposals[0].status).toBe('accepted')
  wrapper.unmount()
})

test('changed StoryThread state disables accepting the stale proposal', () => {
  useNarrativeStore().threads[0].status = 'paid_off'
  const wrapper = mount(WritebackReview)
  expect(wrapper.findAll('button').find((button) => button.text() === '接受')!.attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('状态已变化')
  wrapper.unmount()
})

test('unsupported targets cannot be accepted through UI or store actions', async () => {
  useReviewsStore().writebackProposals[0].target = 'future_target' as WritebackProposal['target']
  const wrapper = mount(WritebackReview)
  expect(wrapper.findAll('button').find((button) => button.text() === '接受')!.attributes('disabled')).toBeDefined()
  await useReviewsStore().updateWritebackStatus('proposal', 'accepted')
  expect(fetchApi).not.toHaveBeenCalled()
  wrapper.unmount()
})
