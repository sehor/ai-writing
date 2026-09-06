import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useMemoryStore } from '../src/stores/memory'

vi.mock('../src/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    activeProjectId: 'a',
    activeProject: { id: 'a' },
  }),
}))
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})

test('opening a scene loads every contract field instead of a blank editor', async () => {
  const manuscript = useManuscriptStore()
  const scene = {
    ...manuscript.createEmptySceneDraft(),
    id: 'scene',
    project_id: 'a',
    title: '来信',
    outcome: '留下来',
    information_delta: '发现署名',
    character_state_delta: '恢复信心',
    story_thread_actions: 'letter:advance',
  }
  manuscript.sceneContracts = [scene]
  manuscript.activeSceneId = scene.id
  await nextTick()
  expect(manuscript.sceneDraft).toMatchObject({
    title: '来信',
    outcome: '留下来',
    information_delta: '发现署名',
    character_state_delta: '恢复信心',
    story_thread_actions: 'letter:advance',
  })
})
test('opening memory and chapter entries displays their saved content', async () => {
  const memory = useMemoryStore()
  memory.memoryRecords = [
    {
      ...memory.createEmptyMemoryDraft(),
      id: 'memory',
      project_id: 'a',
      title: '克制的语气',
      content: '用具体动作代替情绪标签。',
    },
  ]
  memory.activeMemoryId = 'memory'
  const manuscript = useManuscriptStore()
  manuscript.manuscriptChapters = [
    {
      id: 'chapter',
      project_id: 'a',
      title: '潮水',
      sequence: 1,
      summary: '一封信改变了回乡计划。',
    },
  ]
  manuscript.activeChapterId = 'chapter'
  await nextTick()
  expect(memory.memoryDraft.content).toBe('用具体动作代替情绪标签。')
  expect(manuscript.chapterDraft.summary).toBe('一封信改变了回乡计划。')
})
