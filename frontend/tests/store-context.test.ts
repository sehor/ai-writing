import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { fetchApi } from '../src/api/client'
import { useProjectContextStore } from '../src/stores/projectContext'
import { useCanonStore } from '../src/stores/canon'
import { useMemoryStore } from '../src/stores/memory'
import { useGraphStore } from '../src/stores/graph'
import { useProjectsStore } from '../src/stores/projects'
import { useBackupsStore } from '../src/stores/backups'
import { useSnowflakeStore } from '../src/stores/snowflake'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useReviewsStore } from '../src/stores/reviews'
import type { ManuscriptRevision } from '../src/types'

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  vi.mocked(fetchApi).mockReset()
})

for (const factory of [useCanonStore, useMemoryStore, useGraphStore, useProjectsStore, useBackupsStore, useSnowflakeStore, useManuscriptStore, useReviewsStore]) {
  test(`${factory.$id} can be assembled with only leaf context and its local helpers`, () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useProjectContextStore().activeProjectId = 'isolated'
    const store = factory(pinia)
    expect(store.$id).toBe(factory.$id)
    const domains = [useCanonStore, useMemoryStore, useGraphStore, useProjectsStore, useBackupsStore, useSnowflakeStore, useManuscriptStore, useReviewsStore]
    for (const other of domains.filter(domain => domain.$id !== factory.$id)) {
      expect(pinia.state.value[other.$id]).toBeUndefined()
    }
    expect(pinia.state.value.workspace).toBeUndefined()
    expect(fetchApi).not.toHaveBeenCalled()
  })
}

test('generation uses leaf project/model selection without constructing the application shell', async () => {
  const context = useProjectContextStore()
  context.activeProjectId = 'selected'
  context.selectedModelProfile = 'author-model'
  const manuscript = useManuscriptStore()
  manuscript.activeSceneId = 'scene'
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json({ id: 'proposal', scene_id: 'scene' }))
  await manuscript.createProposalFromScene(true)
  expect(fetchApi).toHaveBeenCalledWith('/projects/selected/manuscript/proposals/from-scene/scene/provider', expect.objectContaining({
    body: JSON.stringify({ model_profile: 'author-model', allow_fallback: true, allow_repair: true }),
  }))
  expect(manuscript.manuscriptProposals[0]?.id).toBe('proposal')
})

test('review revision source is explicit and a late report cannot cross projects', async () => {
  const context = useProjectContextStore()
  context.activeProjectId = 'a'
  const reviews = useReviewsStore()
  const source = vi.fn(() => [{ id: 'a-revision' } as ManuscriptRevision])
  reviews.configureRevisionSource(source)
  let finish!: (response: Response) => void
  vi.mocked(fetchApi).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const pending = reviews.showLatestConsistencyReport()
  context.activeProjectId = 'b'
  finish(Response.json({ id: 'old-report' }))
  await pending
  expect(source).toHaveBeenCalledWith('a')
  expect(fetchApi).toHaveBeenCalledWith('/projects/a/analysis/consistency/from-revision/a-revision', expect.anything())
  expect(reviews.consistencyReport).toBeNull()
})
