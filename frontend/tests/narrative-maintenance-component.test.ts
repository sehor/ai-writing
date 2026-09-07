import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, test, vi } from 'vitest'
import NarrativePanel from '../src/components/NarrativePanel.vue'
import CanonWorkspace from '../src/components/CanonWorkspace.vue'
import { useNarrativeStore } from '../src/stores/narrative'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useProjectContextStore } from '../src/stores/projectContext'
import type { KnowledgeState, SceneContract, StoryFact } from '../src/types'

const projectId = 'project-1'
const fact: StoryFact = {
  id: 'fact-1', project_id: projectId, subject: '信件', predicate: '作者', value: '当前事实',
  valid_from_scene: 1, valid_to_scene: 5, reader_visible_from: 3, source_ref: 'scene:s1',
  status: 'confirmed', version: 2, updated_at: '2026-09-07T00:00:00Z',
}
const future: StoryFact = {
  ...fact, id: 'future-1', value: '未来隐藏真相', valid_from_scene: 8, valid_to_scene: null,
  reader_visible_from: 10, source_ref: 'author:future', version: 1,
}
const world: KnowledgeState = {
  id: 'world-1', project_id: projectId, fact_id: fact.id, scope: 'world_truth', character: '',
  known_from_scene: 1, source_ref: 'scene:s1', status: 'confirmed', version: 2, updated_at: '',
}
const scene: SceneContract = {
  id: 's4', project_id: projectId, chapter_id: '', sequence: 4, title: '第四场', pov: '林舟',
  goal: '', conflict: '', turning_point: '', outcome: '', required_canon: '', forbidden_facts: '',
  information_delta: '', character_state_delta: '', story_thread_actions: '', open_threads: '',
  source_artifact_step: 8,
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.restoreAllMocks()
  useProjectContextStore().activeProjectId = projectId
  const manuscript = useManuscriptStore()
  manuscript.sceneContracts = [scene]
  manuscript.activeSceneId = scene.id
  const narrative = useNarrativeStore()
  narrative.facts = [fact, future]
  narrative.activeFactId = fact.id
  narrative.factDraft = { subject: fact.subject, predicate: fact.predicate, value: fact.value, valid_from_scene: 1, valid_to_scene: 5, reader_visible_from: 3, source_ref: fact.source_ref, status: 'confirmed', reason: '' }
  narrative.knowledgeStates = [world]
  narrative.activeKnowledgeId = world.id
  narrative.knowledgeDraft = { scope: 'world_truth', character: '', known_from_scene: 1, source_ref: world.source_ref, status: 'confirmed', reason: '' }
  narrative.storyState = {
    project_id: projectId, scene_position: 4, character: '林舟',
    world_truth: [fact], reader_knowledge: [fact], character_knowledge: [],
  }
})

test('maintenance view shows author facts, editable knowledge controls, and a safety-filtered three-way scene preview', () => {
  const wrapper = mount(NarrativePanel, { props: { mode: 'maintenance' } })
  expect(wrapper.text()).toContain('时态事实与知识')
  expect(wrapper.get('[data-testid="fact-list"]').text()).toContain('未来隐藏真相')
  expect(wrapper.text()).toContain('新建事实')
  expect(wrapper.text()).toContain('新建读者知识')
  expect(wrapper.text()).toContain('新建角色知识')
  expect(wrapper.get('[aria-label="知识状态编辑器"]').text()).toContain('世界真相由事实派生')

  const preview = wrapper.get('[aria-label="场景知识预览"]')
  expect(preview.text()).toContain('世界真相')
  expect(preview.text()).toContain('读者已知')
  expect(preview.text()).toContain('林舟已知')
  expect(preview.text()).toContain('scene:s1')
  expect(preview.text()).not.toContain('未来隐藏真相')
  expect(wrapper.get('[aria-label="预览场景"]').element).toHaveProperty('value', '4')
  expect(wrapper.get('[aria-label="预览角色"]').element).toHaveProperty('value', '林舟')
  wrapper.unmount()
})

test('Canon keeps temporal fact maintenance in the existing author navigation instead of a second top-level system', () => {
  const wrapper = mount(CanonWorkspace)
  expect(wrapper.text()).toContain('已确认的故事事实')
  expect(wrapper.text()).toContain('时态事实与知识')
  expect(wrapper.findComponent(NarrativePanel).props('mode')).toBe('maintenance')
  wrapper.unmount()
})
