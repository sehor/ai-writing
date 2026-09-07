import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import AnalysisExecution from '../src/components/manuscript/AnalysisExecution.vue'
import type { OutboxJob } from '../src/types'

const base = { id: 'j', status: 'succeeded', job_type: 'clp_extraction', aggregate_id: 'r', payload: {}, attempt_count: 1 } as OutboxJob

test('a successful disabled job is shown as not executed, not a clean semantic report', () => {
  const wrapper = mount(AnalysisExecution, { props: { job: { ...base, execution: {
    mode: 'not_configured', processor: 'disabled', outcome: 'not_executed', semantic_review: false,
    source_ref: 'manuscript_revision:r', limitations: 'CLP 未配置，未执行抽取。',
  } } } })
  expect(wrapper.text()).toContain('未执行')
  expect(wrapper.text()).toContain('未配置')
  expect(wrapper.text()).toContain('manuscript_revision:r')
})

test.each(['limited', 'failed'] as const)('shows the actual %s outcome and limitations', (outcome) => {
  const wrapper = mount(AnalysisExecution, { props: { job: { ...base, execution: {
    mode: 'local_rules', processor: 'local_consistency', outcome, semantic_review: false,
    source_ref: 'manuscript_revision:r', limitations: '不是完整语义审稿',
  } } } })
  expect(wrapper.text()).toContain(outcome === 'failed' ? '失败' : '有限检查')
  expect(wrapper.text()).toContain('不是完整语义审稿')
})

test('old jobs do not acquire invented execution evidence after upgrading', () => {
  const wrapper = mount(AnalysisExecution, { props: { job: base } })
  expect(wrapper.text()).toContain('未知')
})
