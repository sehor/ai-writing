import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, test, vi } from 'vitest'
import CopilotEditor from '../src/components/manuscript/CopilotEditor.vue'
import ReferenceWorkspace from '../src/components/manuscript/ReferenceWorkspace.vue'
import { useCopilotContextStore, type EditorTarget } from '../src/stores/copilotContext'
import { useProjectContextStore } from '../src/stores/projectContext'
import { useReviewsStore } from '../src/stores/reviews'

const text = '前文😀选中秘密。后文'
const target: EditorTarget = { project_id: 'p', scene_id: 's', source_kind: 'accepted_manuscript', proposal_id: '', expected_scene_version: 2 }
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); vi.restoreAllMocks(); useProjectContextStore().activeProjectId = 'p' })

async function capture(value: EditorTarget = target) {
  const wrapper = mount(CopilotEditor, { props: { modelValue: text, target: value, label: '正文' } })
  const textarea = wrapper.get('textarea')
  ;(textarea.element as HTMLTextAreaElement).setSelectionRange(4, 8)
  await textarea.trigger('select')
  await wrapper.get('button').trigger('click')
  return wrapper
}

test.each(['accepted_manuscript', 'proposal_draft'] as const)('captures exact UTF-16 selection and %s target without editing text', async (kind) => {
  const value = { ...target, source_kind: kind, proposal_id: kind === 'proposal_draft' ? 'proposal-1' : '' }
  const wrapper = await capture(value)
  const context = useCopilotContextStore()
  expect(context.request).toMatchObject({ ...value, snapshot_text: text, selected_text: '选中秘密', selection_start: 4, selection_end: 8, selection_mode: 'selection' })
  expect(context.stale).toBe(false)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  wrapper.unmount()
  expect(context.stale).toBe(true)
})

test('no selection explicitly captures the complete scene; empty drafts cannot ask', async () => {
  const wrapper = mount(CopilotEditor, { props: { modelValue: text, target, label: '正文' } })
  expect(wrapper.get('button').text()).toBe('就整场景求助')
  await wrapper.get('button').trigger('click')
  expect(useCopilotContextStore().request).toMatchObject({ selection_mode: 'whole_scene', selected_text: text, selection_start: 0, selection_end: text.length })
  await wrapper.setProps({ modelValue: '  ' })
  expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

test.each([{ scene_id: 'other' }, { expected_scene_version: 3 }, { proposal_id: 'another', source_kind: 'proposal_draft' as const }])('target changes invalidate old selection: %s', async (changes) => {
  const wrapper = await capture()
  const previous = JSON.stringify(useCopilotContextStore().request)
  await wrapper.setProps({ target: { ...target, ...changes } })
  expect(useCopilotContextStore().stale).toBe(true)
  expect(JSON.stringify(useCopilotContextStore().request)).toBe(previous)
  wrapper.unmount()
})

test('changed text blocks requests and project switches remove the old selection', async () => {
  const reviews = useReviewsStore()
  const wrapper = await capture()
  reviews.referenceDraft.author_problem = '更含蓄'
  await wrapper.setProps({ modelValue: text + '新内容' })
  const fetch = vi.spyOn(globalThis, 'fetch')
  await reviews.generateReferenceSuggestion(false)
  expect(fetch).not.toHaveBeenCalled()
  expect(reviews.referenceError).toContain('过期')
  useProjectContextStore().activeProjectId = 'other'
  expect(useCopilotContextStore().request).toBeNull()
  wrapper.unmount()
})

test('reference request carries frozen selection and discards a late result for a changed editor', async () => {
  const reviews = useReviewsStore()
  const wrapper = await capture()
  reviews.referenceDraft.author_problem = '更含蓄'
  let respond!: (value: Response) => void
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise(resolve => { respond = resolve }))
  const pending = reviews.generateReferenceSuggestion(false)
  const body = JSON.parse(String(fetch.mock.calls[0]![1]!.body))
  expect(body.scope_ref).toBe('s')
  expect(body.author_problem).toBe('更含蓄')
  expect(body.editor_context.selected_text).toBe('选中秘密')
  await wrapper.setProps({ modelValue: '新的正文' })
  respond(new Response(JSON.stringify({ id: 'old-suggestion' }), { status: 201 }))
  await pending
  expect(reviews.activeReferenceId).toBe('')
  expect(reviews.referenceSuggestions).toEqual([])
  wrapper.unmount()
})

test('reference panel shows source, blocks stale context, and can return to ordinary requests', async () => {
  useReviewsStore()
  const editor = await capture()
  const panel = mount(ReferenceWorkspace)
  expect(panel.get('[aria-label="求助原文"]').text()).toContain('选中文字')
  expect(panel.get('pre').text()).toBe('选中秘密')
  await editor.setProps({ modelValue: 'changed' })
  expect(panel.get('[role="alert"]').text()).toContain('重新选择')
  expect(panel.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await panel.get('[aria-label="求助原文"] button').trigger('click')
  expect(useCopilotContextStore().request).toBeNull()
  panel.unmount(); editor.unmount()
})
