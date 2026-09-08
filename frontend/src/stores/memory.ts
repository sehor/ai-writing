import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { confirmLeave } from '../composables/useDirtyGuard'
import {
  acknowledgeDraftSave,
  discardSavedScope,
  isScopeDirty,
  persistDraft,
  queueAutosave,
  restoreEntryDraft,
} from '../services/draftSessions'
import type { MemoryDraft, MemoryRecord } from '../types'
import { useGraphStore } from './graph'
import { useProjectContextStore } from './projectContext'

/** Memory / style continuity records and their editor draft. */
export const useMemoryStore = defineStore('memory', () => {
  const context = useProjectContextStore()

  const memoryRecords = ref<MemoryRecord[]>([])
  const activeMemoryId = ref('')
  const memoryDraft = ref<MemoryDraft>(createEmptyMemoryDraft())
  const memoryError = ref('')
  const memoryStatus = ref('')
  const isSavingMemory = ref(false)
  const isDeletingMemory = ref(false)

  /** Set while a save/programmatic change moves a selection itself. */
  let suppressNextSelectionGuard = false

  const activeMemoryRecord = computed(() =>
    memoryRecords.value.find((record) => record.id === activeMemoryId.value)
  )

  const memoryStateLabel = computed(() => {
    if (memoryStatus.value) {
      return memoryStatus.value
    }
    return activeMemoryRecord.value ? 'Editing Memory / Style record' : 'New Memory / Style record'
  })

  function createEmptyMemoryDraft(): MemoryDraft {
    return {
      record_type: 'chapter_summary',
      title: '',
      scope: '',
      content: '',
      tags: '',
      source_ref: '',
    }
  }

  function isActiveProject(projectId: string) {
    return projectId === context.activeProjectId
  }

  function memoryScopeKey(
    projectId = context.activeProjectId,
    id = activeMemoryId.value
  ): string {
    return `memory:${projectId}:${id || 'new'}`
  }

  let resetting = false
  watch(memoryDraft, () => { if (!resetting) queueAutosave(memoryScopeKey(), () => memoryDraft.value) }, {
    deep: true,
    flush: 'sync',
  })

  let memorySelectionEpoch = 0
  watch(() => memoryScopeKey(), () => { memorySelectionEpoch++ }, { flush: 'sync' })

  watch(activeMemoryId, (next, prev) => {
    if (resetting) return
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = memoryScopeKey(context.activeProjectId, prev)
      if (isScopeDirty(previousScope, memoryDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Memory / Style 编辑' : '新建 Memory 表单')) {
          const outgoingDraft = memoryDraft.value
          suppressNextSelectionGuard = true
          activeMemoryId.value = prev
          memoryDraft.value = outgoingDraft
          return
        }
        persistDraft(previousScope, memoryDraft.value)
      }
    }
    memoryError.value = ''
    memoryStatus.value = ''
    const selected = activeMemoryRecord.value
    const baselineDraft = selected
      ? {
          record_type: selected.record_type,
          title: selected.title,
          scope: selected.scope,
          content: selected.content,
          tags: selected.tags,
          source_ref: selected.source_ref,
        }
      : createEmptyMemoryDraft()
    restoreEntryDraft<MemoryDraft>(memoryScopeKey(), baselineDraft, (cached) => {
      memoryDraft.value = cached
    }, (message) => {
      memoryStatus.value = message
    }, true)
  }, { flush: 'sync' })

  function startNewMemoryRecord() {
    activeMemoryId.value = ''
    if (activeMemoryId.value) return
    memoryDraft.value = createEmptyMemoryDraft()
    memoryStatus.value = ''
    memoryError.value = ''
  }

  async function saveMemoryRecord() {
    memoryError.value = ''
    memoryStatus.value = ''
    const projectId = context.activeProjectId
    const title = memoryDraft.value.title.trim()
    const content = memoryDraft.value.content.trim()

    if (!projectId) {
      memoryError.value = '请先创建或选择项目。'
      return
    }

    if (!title || !content) {
      memoryError.value = '请填写标题和内容。'
      return
    }

    if (isSavingMemory.value) return
    const recordId = activeMemoryId.value
    const requestScope = memoryScopeKey(projectId, recordId)
    const requestEpoch = memorySelectionEpoch
    const snapshot = { ...memoryDraft.value }
    isSavingMemory.value = true
    try {
      const body = JSON.stringify({
        ...memoryDraft.value,
        title,
        content,
        scope: memoryDraft.value.scope.trim(),
        tags: memoryDraft.value.tags.trim(),
        source_ref: memoryDraft.value.source_ref.trim(),
      })
      const url = recordId
        ? `/projects/${projectId}/memory/records/${recordId}`
        : `/projects/${projectId}/memory/records`
      const response = await fetchApi(url, {
        method: recordId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Memory record')
      }
      const saved = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      memoryRecords.value = [
        ...memoryRecords.value.filter((record) => record.id !== saved.id),
        saved,
      ].sort((left, right) =>
        `${left.record_type}:${left.title}`.localeCompare(`${right.record_type}:${right.title}`)
      )
      if (requestEpoch !== memorySelectionEpoch) return
      const current = { ...memoryDraft.value }
      acknowledgeDraftSave(requestScope, snapshot, current)
      if (activeMemoryId.value !== saved.id) {
        // Only an actual selection change may bypass its guard.
        suppressNextSelectionGuard = true
        activeMemoryId.value = saved.id
        memoryDraft.value = current
        discardSavedScope(requestScope, snapshot)
        acknowledgeDraftSave(memoryScopeKey(projectId, saved.id), snapshot, current)
      }
      memoryStatus.value = 'Memory / Style record saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      if (!isActiveProject(projectId) || requestEpoch !== memorySelectionEpoch) return
      memoryError.value = 'Memory save failed. Check that the API is running.'
    } finally {
      isSavingMemory.value = false
    }
  }

  async function deleteMemoryRecord() {
    memoryError.value = ''
    memoryStatus.value = ''
    const projectId = context.activeProjectId
    const recordId = activeMemoryId.value

    if (!projectId || !recordId) {
      memoryError.value = 'Select a Memory / Style record first.'
      return
    }

    isDeletingMemory.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/memory/records/${recordId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Memory record')
      }
      if (!isActiveProject(projectId)) {
        return
      }
      memoryRecords.value = memoryRecords.value.filter((record) => record.id !== recordId)
      startNewMemoryRecord()
      memoryStatus.value = 'Memory / Style record deleted.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      memoryError.value = 'Memory delete failed. Check that the API is running.'
    } finally {
      isDeletingMemory.value = false
    }
  }

  /** Drop project-scoped state before the workspace loads another project. */
  function resetProjectState() {
    resetting = true
    memoryRecords.value = []
    activeMemoryId.value = ''
    memoryDraft.value = createEmptyMemoryDraft()
    memoryError.value = ''
    memoryStatus.value = ''
    resetting = false
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [[memoryScopeKey(), () => memoryDraft.value]]
  }

  return {
    memoryRecords,
    activeMemoryId,
    memoryDraft,
    memoryError,
    memoryStatus,
    isSavingMemory,
    isDeletingMemory,
    activeMemoryRecord,
    memoryStateLabel,
    createEmptyMemoryDraft,
    memoryScopeKey,
    startNewMemoryRecord,
    saveMemoryRecord,
    deleteMemoryRecord,
    resetProjectState,
    draftSnapshotEntries,
  }
})
