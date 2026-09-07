import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { loadDraft } from '../src/services/draftCache'
import { useNarrativeStore } from '../src/stores/narrative'
import { useProjectContextStore } from '../src/stores/projectContext'
import type { KnowledgeState, StoryFact } from '../src/types'

const projectId = 'project-1'
const fact: StoryFact = {
  id: 'fact-1', project_id: projectId, subject: '信件', predicate: '作者', value: '林舟',
  valid_from_scene: 1, valid_to_scene: 5, reader_visible_from: 3, source_ref: 'scene:s1',
  status: 'confirmed', version: 1, updated_at: '2026-09-07T00:00:00Z',
}
const world: KnowledgeState = {
  id: 'world-1', project_id: projectId, fact_id: fact.id, scope: 'world_truth', character: '',
  known_from_scene: 1, source_ref: 'scene:s1', status: 'confirmed', version: 1, updated_at: '',
}
const reader: KnowledgeState = {
  id: 'reader-1', project_id: projectId, fact_id: fact.id, scope: 'reader_knowledge', character: '',
  known_from_scene: 3, source_ref: 'scene:s1', status: 'confirmed', version: 1, updated_at: '',
}
const character: KnowledgeState = {
  id: 'char-1', project_id: projectId, fact_id: fact.id, scope: 'character_knowledge', character: '林舟',
  known_from_scene: 4, source_ref: 'scene:s2', status: 'confirmed', version: 1, updated_at: '',
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.useFakeTimers()
  vi.restoreAllMocks()
  useProjectContextStore().activeProjectId = projectId
})

afterEach(() => vi.useRealTimers())

test('loads author-visible facts and hydrates the selected fact with knowledge/history without mixing them into preview', async () => {
  const store = useNarrativeStore()
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input)
    if (url.includes('/story-facts/fact-1/knowledge-states')) return Promise.resolve(json([world, reader, character]))
    if (url.includes('/story-facts/fact-1/history')) return Promise.resolve(json([]))
    return Promise.reject(new Error(`Unexpected request ${url}`))
  })
  store.facts = [fact]

  await store.selectFact(fact.id)

  expect(store.activeFactId).toBe(fact.id)
  expect(store.factDraft).toMatchObject({ subject: '信件', value: '林舟', valid_from_scene: 1, reason: '' })
  expect(store.knowledgeStates).toEqual([world, reader, character])
  expect(store.history).toEqual([])
  expect(store.storyState).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(2)
})

test('fact drafts autosave, restore, validate scene windows, and correction sends the current version plus author reason', async () => {
  const store = useNarrativeStore()
  store.facts = [fact]
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json([world, reader, character])).mockResolvedValueOnce(json([]))
  await store.selectFact(fact.id)
  store.factDraft.value = '本地未保存的更正'
  await vi.advanceTimersByTimeAsync(400)
  expect(loadDraft(store.factScopeKey())?.value).toMatchObject({ value: '本地未保存的更正' })

  store.reset()
  store.facts = [fact]
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json([world, reader, character])).mockResolvedValueOnce(json([]))
  await store.selectFact(fact.id)
  expect(store.factDraft.value).toBe('本地未保存的更正')
  expect(store.factStatus).toContain('已恢复本地草稿')

  store.factDraft.valid_from_scene = 5
  store.factDraft.valid_to_scene = 4
  const fetch = vi.spyOn(globalThis, 'fetch')
  const beforeInvalidSave = fetch.mock.calls.length
  await store.saveFact()
  expect(store.factError).toContain('结束场景')
  expect(fetch).toHaveBeenCalledTimes(beforeInvalidSave)

  store.factDraft.valid_from_scene = 1
  store.factDraft.valid_to_scene = 5
  store.factDraft.reader_visible_from = 3
  store.factDraft.reason = '作者核对原始信件'
  const corrected = { ...fact, value: '本地未保存的更正', version: 2 }
  const correctionIndex = fetch.mock.calls.length
  fetch.mockResolvedValueOnce(json(corrected)).mockResolvedValueOnce(json([world, { ...reader, version: 2 }])).mockResolvedValueOnce(json([]))
  await store.saveFact()
  const correctionCall = fetch.mock.calls[correctionIndex]
  expect(String(correctionCall?.[0])).toContain('/story-facts/fact-1')
  expect(correctionCall?.[1]?.method).toBe('PUT')
  expect(JSON.parse(String(correctionCall?.[1]?.body))).toMatchObject({ expected_version: 1, reason: '作者核对原始信件', value: '本地未保存的更正' })
  expect(store.facts[0]?.version).toBe(2)
  expect(store.factStatus).toContain('已保存')
})

test('authors can create and correct reader/character knowledge while world truth remains read-only', async () => {
  const store = useNarrativeStore()
  store.facts = [fact]
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json([world, reader])).mockResolvedValueOnce(json([]))
  await store.selectFact(fact.id)
  store.startNewKnowledge('character_knowledge')
  store.knowledgeDraft.character = '顾宁'
  store.knowledgeDraft.known_from_scene = 4
  store.knowledgeDraft.source_ref = 'scene:s4'
  store.knowledgeDraft.reason = '顾宁亲眼看见'
  const created = { ...character, id: 'char-2', character: '顾宁' }
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(created, 201)).mockResolvedValueOnce(json([world, reader, created])).mockResolvedValueOnce(json([]))
  await store.saveKnowledge()
  expect(fetch.mock.calls[2]?.[1]?.method).toBe('POST')
  expect(JSON.parse(String(fetch.mock.calls[2]?.[1]?.body))).toMatchObject({ scope: 'character_knowledge', character: '顾宁', known_from_scene: 4, reason: '顾宁亲眼看见' })
  expect(store.activeKnowledgeId).toBe(created.id)

  store.selectKnowledge(world.id)
  expect(store.knowledgeReadOnly).toBe(true)
  await store.saveKnowledge()
  expect(store.knowledgeError).toContain('世界真相')

  store.selectKnowledge(created.id)
  store.knowledgeDraft.known_from_scene = 5
  store.knowledgeDraft.reason = '更正获知时点'
  const updated = { ...created, known_from_scene: 5, version: 2 }
  fetch.mockResolvedValueOnce(json(updated)).mockResolvedValueOnce(json([world, reader, updated])).mockResolvedValueOnce(json([]))
  await store.saveKnowledge()
  expect(fetch.mock.calls.at(-3)?.[1]?.method).toBe('PUT')
  expect(JSON.parse(String(fetch.mock.calls.at(-3)?.[1]?.body))).toMatchObject({ expected_version: 1, character: '顾宁', known_from_scene: 5, reason: '更正获知时点' })
})

test('failed scene preview can be retried and does not replace the last safe snapshot', async () => {
  const store = useNarrativeStore()
  const previous = {
    project_id: projectId, scene_position: 3, character: '',
    world_truth: [fact], reader_knowledge: [], character_knowledge: [],
  }
  store.storyState = previous
  const fetch = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(json({ detail: 'temporary failure' }, 503))
    .mockResolvedValueOnce(json({ ...previous, scene_position: 4, reader_knowledge: [fact] }))

  expect(await store.loadStoryState(4, '')).toBe(false)
  expect(store.previewError).toContain('temporary failure')
  expect(store.storyState).toEqual(previous)
  expect(store.isLoadingPreview).toBe(false)

  expect(await store.loadStoryState(4, '')).toBe(true)
  expect(store.previewError).toBe('')
  expect(store.storyState?.scene_position).toBe(4)
  expect(store.storyState?.reader_knowledge).toEqual([fact])
  expect(fetch).toHaveBeenCalledTimes(2)
})

test('later scene preview wins when an older request resolves last', async () => {
  const store = useNarrativeStore()
  let resolveFirst!: (response: Response) => void
  let resolveSecond!: (response: Response) => void
  vi.spyOn(globalThis, 'fetch')
    .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveFirst = resolve }))
    .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveSecond = resolve }))

  const first = store.loadStoryState(4, '林舟')
  const second = store.loadStoryState(5, '顾宁')
  resolveSecond(json({ project_id: projectId, scene_position: 5, character: '顾宁', world_truth: [], reader_knowledge: [], character_knowledge: [] }))
  await second
  resolveFirst(json({ project_id: projectId, scene_position: 4, character: '林舟', world_truth: [fact], reader_knowledge: [fact], character_knowledge: [fact] }))
  await first

  expect(store.storyState?.scene_position).toBe(5)
  expect(store.storyState?.character).toBe('顾宁')
  expect(store.previewStatus).toContain('场景 5')
  expect(store.isLoadingPreview).toBe(false)
})

test('scene preview uses only the story-state safety endpoint and separates world, reader, and character visibility', async () => {
  const store = useNarrativeStore()
  store.facts = [{ ...fact, value: '未来隐藏真相', valid_from_scene: 8, reader_visible_from: 10 }]
  const previewFact = { ...fact, value: '当前事实' }
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({
    project_id: projectId,
    scene_position: 4,
    character: '林舟',
    world_truth: [previewFact],
    reader_knowledge: [previewFact],
    character_knowledge: [],
  }))

  await store.loadStoryState(4, '林舟')

  expect(String(fetch.mock.calls[0]?.[0])).toContain('/story-state?scene_position=4&character=')
  expect(store.storyState?.world_truth.map(item => item.value)).toEqual(['当前事实'])
  expect(store.storyState?.reader_knowledge.map(item => item.value)).toEqual(['当前事实'])
  expect(store.storyState?.character_knowledge).toEqual([])
  expect(JSON.stringify(store.storyState)).not.toContain('未来隐藏真相')
})
