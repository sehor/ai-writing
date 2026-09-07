import { mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import GenerationReview from '../src/components/manuscript/GenerationReview.vue'
import type { ManuscriptProposal } from '../src/types'

const proposal: ManuscriptProposal = {
  id: 'review', project_id: 'p', scene_id: 's', source: 'scene_contract', title: 'Draft', content: 'Original prose',
  context: '', checklist: [], status: 'pending_review', created_at: '', reviewed_at: '',
  generation_review: {
    schema_version: 1, availability: 'structured', provider: 'fake', model: 'test', generation_run_id: 'run-1',
    material: { scene_id: 's', manuscript_prose: 'Original prose', entry_state_observed: ['门关着'], exit_state_produced: ['门打开'],
      scene_contract_coverage: { goal: '目标已覆盖', conflict: '冲突已覆盖', turning_point: '转折已覆盖', outcome: '结果已覆盖', missing_elements: ['代价'] },
      new_fact_candidates: [{ claim: '钥匙是黄铜的', reason_introduced: '解释开锁', entity_refs: ['钥匙'], status: 'proposal' }],
      design_deviation_proposals: [{ target_artifact_ref: 'step:8', current_design: '门保持关闭', proposed_change: '打开门', reason: '推动情节', downstream_impact: ['修改下一场景'] }],
      continuity_questions: ['谁持有钥匙？'], source_refs: ['scene:s'],
    },
  },
}
beforeEach(() => { localStorage.clear() })

test('shows complete material and restores independent per-proposal review choices after remount', async () => {
  const original = JSON.stringify(proposal)
  let wrapper = mount(GenerationReview, { props: { projectId: 'p', proposal } })
  for (const text of ['门关着', '门打开', '目标已覆盖', '钥匙是黄铜的', '门保持关闭', '打开门', '推动情节', '修改下一场景', '谁持有钥匙？', '代价', 'scene:s', 'run-1']) {
    expect(wrapper.text()).toContain(text)
  }
  await wrapper.get('select[aria-label="设计偏差 1处理状态"]').setValue('reviewed')
  await wrapper.get('select[aria-label="连续性问题 1处理状态"]').setValue('question')
  expect(wrapper.text()).toContain('2 项待处理 · 1 项已核对 · 1 项保留疑问')
  wrapper.unmount()
  wrapper = mount(GenerationReview, { props: { projectId: 'p', proposal } })
  expect((wrapper.get('select[aria-label="设计偏差 1处理状态"]').element as HTMLSelectElement).value).toBe('reviewed')
  await wrapper.setProps({ proposal: { ...proposal, id: 'another' } })
  expect(wrapper.text()).toContain('4 项待处理')
  expect(JSON.stringify(proposal)).toBe(original)
})

test('legacy material is explicitly missing and cache failure is visible', async () => {
  const wrapper = mount(GenerationReview, { props: { projectId: 'p', proposal: { ...proposal, generation_review: null } } })
  expect(wrapper.text()).toContain('没有结构化审核材料')
  await wrapper.setProps({ proposal })
  vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => { throw new Error('quota') })
  await wrapper.get('select').setValue('reviewed')
  expect(wrapper.get('[role="alert"]').text()).toContain('未能保存')
})
