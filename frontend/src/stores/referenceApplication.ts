import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ReferenceEditorContext, ReferenceSuggestion } from '../types/reference'
import { useCopilotContextStore } from './copilotContext'
import { useManuscriptStore } from './manuscript'
import { useProposalDraftStore } from './proposalDraft'

export type ReferenceApplyMode = 'replace' | 'insert'

type TargetState = {
  text: string
  write: (value: string) => void
}

type UndoRecord = {
  suggestionId: string
  context: ReferenceEditorContext
  before: string
  after: string
}

export const useReferenceApplicationStore = defineStore('referenceApplication', () => {
  const copilot = useCopilotContextStore()
  const manuscript = useManuscriptStore()
  const proposalDraft = useProposalDraftStore()
  const activeSuggestionId = ref('')
  const applicationText = ref('')
  const mode = ref<ReferenceApplyMode>('replace')
  const previewText = ref('')
  const error = ref('')
  const status = ref('')
  const undoRecord = ref<UndoRecord | null>(null)

  watch([applicationText, mode], () => {
    previewText.value = ''
    if (status.value.startsWith('预览')) status.value = ''
  }, { flush: 'sync' })

  function selectSuggestion(suggestion: ReferenceSuggestion | null) {
    const nextId = suggestion?.id ?? ''
    if (activeSuggestionId.value === nextId) return
    activeSuggestionId.value = nextId
    applicationText.value = ''
    mode.value = 'replace'
    previewText.value = ''
    error.value = ''
    status.value = ''
  }

  function resolveTarget(context: ReferenceEditorContext): TargetState | null {
    if (context.source_kind === 'proposal_draft') {
      if (
        proposalDraft.projectId !== context.project_id ||
        proposalDraft.proposalId !== context.proposal_id ||
        proposalDraft.expectedSceneVersion !== context.expected_scene_version
      ) return null
      return {
        text: proposalDraft.content,
        write: (value) => { proposalDraft.content = value },
      }
    }
    if (
      manuscript.editingManuscriptSceneId !== context.scene_id ||
      manuscript.manuscriptEditVersion !== context.expected_scene_version ||
      context.proposal_id
    ) return null
    return {
      text: manuscript.manuscriptEditContent,
      write: (value) => { manuscript.manuscriptEditContent = value },
    }
  }

  function buildNextText(current: string, context: ReferenceEditorContext): string | null {
    const text = applicationText.value
    if (!text.trim()) {
      error.value = '请先从建议中选取或整理一段明确要应用的正文。'
      return null
    }
    if (current !== context.snapshot_text) {
      error.value = '原文已变化，请回到编辑器重新选择后再应用。'
      return null
    }
    const { selection_start: start, selection_end: end, selected_text: selected } = context
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end > current.length || end <= start || current.slice(start, end) !== selected) {
      error.value = '求助原文与当前选区不一致，请回到编辑器重新选择。'
      return null
    }
    if (context.selection_mode === 'whole_scene' && (start !== 0 || end !== current.length)) {
      error.value = '整场景求助范围已变化，请回到编辑器重新选择。'
      return null
    }
    const next = mode.value === 'replace'
      ? `${current.slice(0, start)}${text}${current.slice(end)}`
      : `${current.slice(0, end)}${text}${current.slice(end)}`
    if (next === current) {
      error.value = '应用后正文没有变化，请调整待应用文本。'
      return null
    }
    return next
  }

  function prepare(suggestion: ReferenceSuggestion) {
    error.value = ''
    status.value = ''
    const context = suggestion.editor_context
    if (!context || !copilot.matchesEditor(context)) {
      error.value = '原文、目标、版本或编辑会话已变化，请回到编辑器重新选择。'
      return null
    }
    const target = resolveTarget(context)
    if (!target) {
      error.value = '当前草稿目标或版本已变化，请回到编辑器重新选择。'
      return null
    }
    const next = buildNextText(target.text, context)
    return next ? { context, target, next } : null
  }

  function previewSuggestion(suggestion: ReferenceSuggestion) {
    const prepared = prepare(suggestion)
    if (!prepared) {
      previewText.value = ''
      return false
    }
    previewText.value = prepared.next
    status.value = '预览仅展示本地草稿结果，尚未修改正文。'
    return true
  }

  function applySuggestion(suggestion: ReferenceSuggestion) {
    const prepared = prepare(suggestion)
    if (!prepared) return false
    prepared.target.write(prepared.next)
    undoRecord.value = {
      suggestionId: suggestion.id,
      context: prepared.context,
      before: prepared.target.text,
      after: prepared.next,
    }
    previewText.value = prepared.next
    status.value = '已应用到当前本地草稿，尚未保存正式版本。'
    return true
  }

  function targetMatchesUndo(record: UndoRecord) {
    if (!copilot.matchesSession(record.context)) return false
    const target = resolveTarget(record.context)
    return !!target && target.text === record.after
  }

  const canUndo = computed(() => !!undoRecord.value && targetMatchesUndo(undoRecord.value))

  function undo() {
    error.value = ''
    status.value = ''
    const record = undoRecord.value
    if (!record) return false
    if (!copilot.matchesSession(record.context)) {
      error.value = '编辑目标或会话已切换，不能撤销旧操作。'
      return false
    }
    const target = resolveTarget(record.context)
    if (!target) {
      error.value = '当前草稿目标或版本已变化，不能撤销旧操作。'
      return false
    }
    if (target.text !== record.after) {
      error.value = '应用后草稿已继续修改，不能撤销以免覆盖新文本。'
      return false
    }
    target.write(record.before)
    undoRecord.value = null
    previewText.value = ''
    status.value = '已撤销上一次参考建议应用；草稿仍未保存正式版本。'
    return true
  }

  return {
    activeSuggestionId,
    applicationText,
    mode,
    previewText,
    error,
    status,
    canUndo,
    selectSuggestion,
    previewSuggestion,
    applySuggestion,
    undo,
  }
})
