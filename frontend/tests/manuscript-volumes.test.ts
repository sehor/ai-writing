import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, expect, test, vi } from 'vitest'
import { useProjectContextStore } from '../src/stores/projectContext'
import { useManuscriptStore } from '../src/stores/manuscript'
import { loadDraft } from '../src/services/draftCache'
import { organizeManuscript } from '../src/domain/manuscriptOrganization'
import { mount } from '@vue/test-utils'
import VolumeManager from '../src/components/manuscript/VolumeManager.vue'
import type { ManuscriptChapter, SceneContract } from '../src/types'

const volume = { id: 'v1', project_id: 'p', sequence: 1, title: '第一卷', chapter_ids: ['c1'] }
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 })
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); vi.restoreAllMocks(); vi.useFakeTimers(); useProjectContextStore().activeProjectId = 'p'; window.confirm = vi.fn(() => true) })
afterEach(() => { useManuscriptStore().resetVolumes(); vi.useRealTimers() })

test('directory keeps empty volumes, sorts deterministically, and exposes unassigned chapters and scenes once', () => {
  const chapters = [{ id: 'c1', title: '第一章', sequence: 1 }, { id: 'c2', title: '第二章', sequence: 2 }] as ManuscriptChapter[]
  const scenes = [{ id: 's1', title: '开场', chapter_id: 'c1', sequence: 1 }, { id: 's2', title: '散场', chapter_id: '', sequence: 2 }] as SceneContract[]
  const result = organizeManuscript([{ ...volume, sequence: 2 }, { ...volume, id: 'empty', sequence: 1, title: '空卷', chapter_ids: [] }], chapters, scenes)
  expect(result.map(v => v.id)).toEqual(['empty', 'v1', ''])
  expect(result[0]?.groups).toEqual([])
  expect(result.flatMap(v => v.groups.flatMap(g => g.scenes)).map(s => s.id)).toEqual(['s1', 's2'])
  expect(organizeManuscript([volume], chapters, scenes, '第一卷')[0]?.groups[0]?.scenes[0]?.id).toBe('s1')
})

test('volume manager renders an explicit non-destructive delete and scoped save state', async () => {
  const store = useManuscriptStore()
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json([volume]))
  await store.loadManuscriptVolumes()
  store.selectVolume('v1')
  const wrapper = mount(VolumeManager)
  expect(wrapper.get('[aria-label="卷名"]').element).toBeTruthy()
  expect(wrapper.text()).toContain('删除卷，保留章节')
  expect(wrapper.text()).toContain('不会改变场景的叙事时点')
  wrapper.unmount()
})

test('volume form autosaves and restores without changing the server record', async () => {
  const store = useManuscriptStore()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json([volume]))
  await store.loadManuscriptVolumes()
  store.selectVolume('v1')
  store.volumeDraft.title = '未保存卷名'
  await vi.advanceTimersByTimeAsync(400)
  expect(loadDraft(store.volumeScopeKey())?.value).toMatchObject({ title: '未保存卷名' })
  expect(store.manuscriptVolumes[0]?.title).toBe('第一卷')
  store.resetVolumes()
  await store.loadManuscriptVolumes()
  store.selectVolume('v1')
  expect(store.volumeDraft.title).toBe('未保存卷名')
})

test('reverting a cached volume edit does not resurrect it on return', async () => {
  const store = useManuscriptStore()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json([volume]))
  await store.loadManuscriptVolumes(); store.selectVolume('v1')
  store.volumeDraft.title = 'discarded'; vi.advanceTimersByTime(500)
  store.volumeDraft.title = volume.title
  store.selectVolume(''); store.selectVolume('v1')
  expect(store.volumeDraft.title).toBe(volume.title)
  expect(loadDraft(store.volumeScopeKey())).toBeNull()
})

test('saving and chapter movement never call a manuscript content endpoint', async () => {
  const store = useManuscriptStore()
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json([volume]))
  await store.loadManuscriptVolumes()
  store.selectVolume('v1')
  store.volumeDraft.title = '新卷名'
  fetch.mockResolvedValueOnce(json({ ...volume, title: '新卷名' }))
  await store.saveVolume()
  expect(fetch.mock.calls[1]?.[0]).toContain('/manuscript/volumes/v1')
  expect(store.manuscriptVolumes[0]?.title).toBe('新卷名')
  fetch.mockResolvedValueOnce(json({ chapter_id: 'c1', volume_id: '' }))
  await store.assignChapterVolume('c1', '')
  expect(store.manuscriptVolumes[0]?.chapter_ids).toEqual([])
  expect(fetch.mock.calls[2]?.[0]).toContain('/chapters/c1/volume')
})

test('switching projects invalidates a late volume load', async () => {
  const store = useManuscriptStore()
  let resolve!: (value: Response) => void
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise(r => { resolve = r }))
  const pending = store.loadManuscriptVolumes()
  store.resetVolumes()
  useProjectContextStore().activeProjectId = 'other'
  resolve(json([volume]))
  await pending
  expect(store.manuscriptVolumes).toEqual([])
})

test('cancelled switches and invalid ranges preserve the current volume draft', async () => {
  const store = useManuscriptStore()
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json([volume]))
  await store.loadManuscriptVolumes()
  store.selectVolume('v1')
  store.volumeDraft.title = '不能丢失'
  vi.mocked(window.confirm).mockReturnValue(false)
  store.selectVolume('')
  expect(store.activeVolumeId).toBe('v1')
  store.volumeDraft.sequence = 1000
  await store.saveVolume()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(store.volumeError).toContain('999')
})
