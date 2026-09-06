import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { confirmLeave } from '../composables/useDirtyGuard'
import { clearDraft } from '../services/draftCache'
import {
  isScopeDirty,
  persistDraft,
  queueAutosave,
  restoreEntryDraft,
} from '../services/draftSessions'
import type { MemoryDraft, MemoryRecord } from '../types'
import { useGraphStore } from './graph'
import { useWorkspaceStore } from './workspace'
import type { WorkspaceShell } from './workspaceShell'

/** Memory / style continuity records and their editor draft. */
export const useMemoryStore = defineStore('memory', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }

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
    return projectId === ws().activeProjectId
  }

  function memoryScopeKey(
    projectId = ws().activeProjectId,
    id = activeMemoryId.value
  ): string {
    return `memory:${projectId}:${id || 'new'}`
  }

  watch(memoryDraft, () => queueAutosave(memoryScopeKey(), () => memoryDraft.value), {
    deep: true,
  })

  watch(activeMemoryId, (next, prev) => {
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = memoryScopeKey(ws().activeProjectId, prev)
      if (isScopeDirty(previousScope, memoryDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Memory / Style 编辑' : '新建 Memory 表单')) {
          suppressNextSelectionGuard = true
          activeMemoryId.value = prev
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
    memoryDraft.value = baselineDraft
    restoreEntryDraft<MemoryDraft>(memoryScopeKey(), baselineDraft, (cached) => {
      memoryDraft.value = cached
    }, (message) => {
      memoryStatus.value = message
    })
  })

  function startNewMemoryRecord() {
    activeMemoryId.value = ''
    memoryDraft.value = createEmptyMemoryDraft()
    memoryStatus.value = ''
    memoryError.value = ''
  }

  async function saveMemoryRecord() {
    memoryError.value = ''
    memoryStatus.value = ''
    const projectId = ws().activeProject?.id
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
      const url = activeMemoryId.value
        ? `/projects/${projectId}/memory/records/${activeMemoryId.value}`
        : `/projects/${projectId}/memory/records`
      const response = await fetchApi(url, {
        method: activeMemoryId.value ? 'PUT' : 'POST',
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
      clearDraft(memoryScopeKey(projectId, activeMemoryId.value))
      suppressNextSelectionGuard = true
      activeMemoryId.value = saved.id
      memoryStatus.value = 'Memory / Style record saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      memoryError.value = 'Memory save failed. Check that the API is running.'
    } finally {
      isSavingMemory.value = false
    }
  }

  async function deleteMemoryRecord() {
    memoryError.value = ''
    memoryStatus.value = ''
    const projectId = ws().activeProject?.id
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
    memoryRecords.value = []
    activeMemoryId.value = ''
    memoryDraft.value = createEmptyMemoryDraft()
    memoryError.value = ''
    memoryStatus.value = ''
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
