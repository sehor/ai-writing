import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import SnowflakeWorkspace from '../src/components/SnowflakeWorkspace.vue'
import { useSnowflakeStore } from '../src/stores/snowflake'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useWorkspaceStore } from '../src/stores/workspace'
import type { SceneContract, SceneProposal, SnowflakeArtifactRevision, SnowflakeStep } from '../src/types'

// Keep navigation explicit without loading a whole project's HTTP surfaces.
vi.mock('../src/stores/workspace', async () => {
  const { defineStore, storeToRefs } = await import('pinia')
  const { ref, computed } = await import('vue')
  const { useProjectContextStore } = await import('../src/stores/projectContext')
  const { useSnowflakeStore } = await import('../src/stores/snowflake')
  return { useWorkspaceStore: defineStore('test-workspace', () => {
    const context = useProjectContextStore()
    context.activeProjectId = 'project'
    const { activeStepNumber } = storeToRefs(context)
    const activeProject = ref({ id: 'project' })
    const activeSection = ref('snowflake')
    const activeStep = computed(() => useSnowflakeStore().steps.find(step => step.number === activeStepNumber.value))
    function selectStep(step: number) { activeStepNumber.value = step }
    return { activeStepNumber, activeProject, activeStep, activeSection, selectStep }
  }) }
})

let pinia = createPinia()
let wrapper: VueWrapper
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  vi.useFakeTimers()
  useSnowflakeStore().steps = Array.from({ length: 10 }, (_, i) => ({
    number: i + 1, title: `规划 ${i + 1}`, description: `说明 ${i + 1}`,
    artifact: `artifact-${i + 1}`, dependencies: i ? [i] : [], virtual: i === 9,
  } as SnowflakeStep))
  vi.spyOn(useManuscriptStore(), 'refreshSceneContracts').mockResolvedValue()
})
afterEach(() => {
  wrapper?.unmount()
  vi.runAllTimers()
  disposePinia(pinia)
  vi.useRealTimers()
  vi.restoreAllMocks()
})
function render() {
  wrapper = mount(SnowflakeWorkspace, { global: { stubs: { SnowflakeRecords: true, SnowflakeRevisionHistory: true } } })
}
async function open(step: number) {
  await wrapper.get(`button[aria-label="Open step ${step}: 规划 ${step}"]`).trigger('click')
}

test('step cards navigate and artifact inputs share the existing draft and generation state', async () => {
  const store = useSnowflakeStore()
  const generate = vi.spyOn(store, 'generateArtifact').mockResolvedValue()
  const save = vi.spyOn(store, 'saveArtifact').mockResolvedValue()
  render()
  expect(wrapper.get('.step-selector').text()).toContain('说明 1')
  await open(1)
  await wrapper.get('.artifact-editor > textarea').setValue('Author draft')
  expect(store.artifactDraft).toBe('Author draft')
  await wrapper.findAll('button').find(button => button.text() === '保存草稿版本')!.trigger('click')
  expect(save).toHaveBeenCalledOnce()
  const budget = wrapper.get('input[type="number"]')
  expect(budget.attributes()).toMatchObject({ min: '1000', max: '400000' })
  await budget.setValue('12000')
  await wrapper.get('.generation-instruction textarea').setValue('Add tension')
  await wrapper.findAll('button').find(button => button.text() === '生成草稿')!.trigger('click')
  expect(generate).toHaveBeenCalledOnce()
  expect(store.previousArtifactsContextChars).toBe(12000)
  expect(store.generationInstruction).toBe('Add tension')
  await wrapper.get('.back-to-steps').trigger('click')
  await open(6)
  expect(wrapper.find('.artifact-editor > textarea').exists()).toBe(false)
  expect(wrapper.findAll('.generation-mode option').map(option => option.attributes('value'))).toEqual(['record_set', 'selection', 'continue'])
  expect(wrapper.find('snowflake-records-stub').exists()).toBe(true)
  expect(wrapper.find('snowflake-revision-history-stub').exists()).toBe(false)
})

test('compiler review renders update evidence and uses the existing selection and review actions', async () => {
  const store = useSnowflakeStore()
  store.sceneProposals = [{
    id: 'proposal', sequence: 1, title: '场景', operation: 'update', source_record_id: 'record',
    expected_plan_version: 2, changes: { title: { before: '旧标题', after: '新标题' } },
    blocking_errors: [], warnings: [], status: 'pending_review',
  } as SceneProposal]
  const accept = vi.spyOn(store, 'acceptSceneProposalBatch').mockResolvedValue()
  const reject = vi.spyOn(store, 'rejectSceneProposal').mockResolvedValue()
  render()
  await open(8)
  expect(wrapper.get('.scene-update-review').text()).toContain('旧标题')
  expect(wrapper.get('.scene-update-review').text()).toContain('新标题')
  await wrapper.get('input[type="checkbox"]').setValue(true)
  expect(store.selectedSceneProposalIds).toEqual(['proposal'])
  await wrapper.findAll('button').find(button => button.text().startsWith('Accept Selected'))!.trigger('click')
  expect(accept).toHaveBeenCalledWith(false)
  await wrapper.findAll('button').find(button => button.text() === '拒绝')!.trigger('click')
  expect(reject).toHaveBeenCalledWith('proposal')
})

test('legacy selected prose survives navigation and imports through the review action', async () => {
  const store = useSnowflakeStore()
  store.revisions = [{ id: 'legacy', status: 'legacy_draft', content: 'Selected prose. Remaining prose.' } as SnowflakeArtifactRevision]
  useManuscriptStore().sceneContracts = [{ id: 'scene', sequence: 1, title: '目标' } as SceneContract]
  const importSelection = vi.spyOn(store, 'importLegacyDraftSelection').mockResolvedValue({ id: 'proposal' })
  render()
  await open(10)
  await wrapper.get('.legacy-import-form select').setValue('scene')
  const source = wrapper.get<HTMLTextAreaElement>('textarea[aria-label="Preserved legacy Step 10 draft"]')
  source.element.setSelectionRange(0, 15)
  await source.trigger('select')
  await wrapper.get('.back-to-steps').trigger('click')
  expect(wrapper.find('.legacy-import-form').exists()).toBe(false)
  await open(1)
  await wrapper.get('.back-to-steps').trigger('click')
  await open(10)
  expect(wrapper.get<HTMLTextAreaElement>('.legacy-import-form textarea').element.value).toBe('Selected prose.')
  expect(wrapper.get<HTMLInputElement>('.legacy-import-form input').element.value).toBe('目标')
  await wrapper.findAll('button').find(button => button.text() === '导入选文并审核')!.trigger('click')
  expect(importSelection).toHaveBeenCalledExactlyOnceWith('legacy', 'scene', '目标', 'Selected prose.')
  await nextTick()
  expect(wrapper.get<HTMLTextAreaElement>('.legacy-import-form textarea').element.value).toBe('')
  await wrapper.findAll('button').find(button => button.text() === '进入正文写作')!.trigger('click')
  expect(useWorkspaceStore().activeSection).toBe('manuscript')
})
