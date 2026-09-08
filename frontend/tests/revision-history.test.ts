import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import RevisionHistory from '../src/components/manuscript/RevisionHistory.vue'
import { useManuscriptStore } from '../src/stores/manuscript'
import type { ManuscriptRevision } from '../src/types'

beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
test('history bounds rendered rows, expands only requested prose, and retains off-page selections and actions', async () => {
  const store = useManuscriptStore()
  store.manuscriptRevisions = Array.from({ length: 121 }, (_, i) => ({ id: `r${i}`, project_id: 'p', scene_id: `s${i % 2}`,
    proposal_id: '', title: `Version ${i}`, content: `Author text ${i}`, version: i + 1, created_at: '' })) as ManuscriptRevision[]
  store.diffLeftRevisionId = 'r120'; store.diffRightRevisionId = 'r100'
  const restore = vi.spyOn(store, 'restoreRevision').mockResolvedValue(undefined)
  const wrapper = mount(RevisionHistory)
  expect(wrapper.findAll('.revision-item')).toHaveLength(50)
  expect(wrapper.findAll('option').length).toBeLessThanOrEqual(104)
  expect(wrapper.findAll('.revision-item pre')).toHaveLength(0)
  const click = async (label: string) => { await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click') }
  await click('查看正文')
  expect(wrapper.findAll('.revision-item pre')).toHaveLength(1)
  expect(wrapper.get('.revision-item pre').text()).toBe('Author text 0')
  await click('下一页'); await click('下一页')
  expect(wrapper.findAll('.revision-item')).toHaveLength(21)
  expect(wrapper.findAll('.revision-item pre')).toHaveLength(0)
  expect(store.revisionCount).toBe(121)
  expect(store.diffLeftRevisionId).toBe('r120')
  expect(store.diffRightRevisionId).toBe('r100')
  await click('恢复版本')
  expect(restore).toHaveBeenCalledWith('r100')
  wrapper.unmount()
})
