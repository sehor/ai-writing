import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ReferenceEditorContext } from '../types/reference'
import { useProjectContextStore } from './projectContext'

export type EditorTarget = Pick<ReferenceEditorContext, 'project_id' | 'scene_id' | 'source_kind' | 'proposal_id' | 'expected_scene_version'>
type EditorSnapshot = EditorTarget & { session_id: string; snapshot_text: string }

/** Ephemeral selection authority. It never owns or saves manuscript text. */
export const useCopilotContextStore = defineStore('copilotContext', () => {
  const context = useProjectContextStore()
  const current = ref<EditorSnapshot | null>(null)
  const request = ref<ReferenceEditorContext | null>(null)
  const captureCount = ref(0)
  const stale = computed(() => !!request.value && !matchesEditor(request.value))

  function matchesSession(value: ReferenceEditorContext) {
    const editor = current.value
    return !!editor && value.project_id === context.activeProjectId &&
      value.project_id === editor.project_id && value.scene_id === editor.scene_id &&
      value.source_kind === editor.source_kind && value.proposal_id === editor.proposal_id &&
      value.expected_scene_version === editor.expected_scene_version && value.session_id === editor.session_id
  }
  function matchesEditor(value: ReferenceEditorContext) {
    return matchesSession(value) && value.snapshot_text === current.value?.snapshot_text
  }
  function isCurrent(value: ReferenceEditorContext) {
    return matchesEditor(value) && JSON.stringify(request.value) === JSON.stringify(value)
  }
  function register(editor: EditorSnapshot) { current.value = { ...editor } }
  function release(sessionId: string) {
    if (current.value?.session_id === sessionId) current.value = null
  }
  function capture(start: number, end: number) {
    const editor = current.value
    if (!editor || editor.project_id !== context.activeProjectId || !editor.snapshot_text.trim()) return
    const whole = start === end
    const left = whole ? 0 : start
    const right = whole ? editor.snapshot_text.length : end
    if (left < 0 || right > editor.snapshot_text.length || right <= left) return
    const selected = editor.snapshot_text.slice(left, right)
    if (!selected.trim()) return
    request.value = { ...editor, selection_mode: whole ? 'whole_scene' : 'selection',
      selection_start: left, selection_end: right, selected_text: selected }
    captureCount.value += 1
  }
  function clear() { request.value = null }
  watch(() => context.activeProjectId, () => { current.value = null; clear() }, { flush: 'sync' })
  return { current, request, stale, captureCount, register, release, capture, clear, matchesSession, matchesEditor, isCurrent }
})
