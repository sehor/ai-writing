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
import type { CanonDraft, CanonEntity } from '../types'
import { useGraphStore } from './graph'
import { useProjectContextStore } from './projectContext'

/** Confirmed story facts (the Canon DB) and their editor draft. */
export const useCanonStore = defineStore('canon', () => {
  const context = useProjectContextStore()

  const canonEntities = ref<CanonEntity[]>([])
  const activeCanonId = ref('')
  const canonDraft = ref<CanonDraft>(createEmptyCanonDraft())
  const canonError = ref('')
  const canonStatus = ref('')
  const isSavingCanon = ref(false)
  const isDeletingCanon = ref(false)

  /** Set while a save/programmatic change moves a selection itself. */
  let suppressNextSelectionGuard = false

  const activeCanonEntity = computed(() =>
    canonEntities.value.find((entity) => entity.id === activeCanonId.value)
  )

  const canonStateLabel = computed(() => {
    if (canonStatus.value) {
      return canonStatus.value
    }
    return activeCanonEntity.value ? '编辑设定' : '新建设定'
  })

  function createEmptyCanonDraft(): CanonDraft {
    return {
      entity_type: 'character',
      name: '',
      summary: '',
      current_state: '',
      constraints: '',
      last_seen: '',
      timeline_notes: '',
    }
  }

  function isActiveProject(projectId: string) {
    return projectId === context.activeProjectId
  }

  function canonScopeKey(
    projectId = context.activeProjectId,
    id = activeCanonId.value
  ): string {
    return `canon:${projectId}:${id || 'new'}`
  }

  let resetting = false
  watch(canonDraft, () => { if (!resetting) queueAutosave(canonScopeKey(), () => canonDraft.value) }, {
    deep: true,
    flush: 'sync',
  })

  let canonSelectionEpoch = 0
  watch(() => canonScopeKey(), () => { canonSelectionEpoch++ }, { flush: 'sync' })

  watch(activeCanonId, (next, prev) => {
    if (resetting) return
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = canonScopeKey(context.activeProjectId, prev)
      if (isScopeDirty(previousScope, canonDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Canon 实体编辑' : '新建 Canon 表单')) {
          const outgoingDraft = canonDraft.value
          suppressNextSelectionGuard = true
          activeCanonId.value = prev
          canonDraft.value = outgoingDraft
          return
        }
        persistDraft(previousScope, canonDraft.value)
      }
    }
    canonError.value = ''
    canonStatus.value = ''
    const selected = activeCanonEntity.value
    const baselineDraft = selected
      ? {
          entity_type: selected.entity_type,
          name: selected.name,
          summary: selected.summary,
          current_state: selected.current_state,
          constraints: selected.constraints,
          last_seen: selected.last_seen,
          timeline_notes: selected.timeline_notes,
        }
      : createEmptyCanonDraft()
    restoreEntryDraft<CanonDraft>(canonScopeKey(), baselineDraft, (cached) => {
      canonDraft.value = cached
    }, (message) => {
      canonStatus.value = message
    }, true)
  }, { flush: 'sync' })

  function startNewCanonEntity() {
    activeCanonId.value = ''
    if (activeCanonId.value) return
    canonDraft.value = createEmptyCanonDraft()
    canonStatus.value = ''
    canonError.value = ''
  }

  async function saveCanonEntity() {
    canonError.value = ''
    canonStatus.value = ''
    const projectId = context.activeProjectId
    const name = canonDraft.value.name.trim()

    if (!projectId) {
      canonError.value = '请先创建或选择项目。'
      return
    }

    if (!name) {
      canonError.value = 'Canon entity name is required.'
      return
    }

    if (isSavingCanon.value) return
    const recordId = activeCanonId.value
    const requestScope = canonScopeKey(projectId, recordId)
    const requestEpoch = canonSelectionEpoch
    const snapshot = { ...canonDraft.value }
    isSavingCanon.value = true
    try {
      const body = JSON.stringify({
        ...canonDraft.value,
        name,
        summary: canonDraft.value.summary.trim(),
        current_state: canonDraft.value.current_state.trim(),
        constraints: canonDraft.value.constraints.trim(),
        last_seen: canonDraft.value.last_seen.trim(),
        timeline_notes: canonDraft.value.timeline_notes.trim(),
      })
      const url = recordId
        ? `/projects/${projectId}/canon/entities/${recordId}`
        : `/projects/${projectId}/canon/entities`
      const response = await fetchApi(url, {
        method: recordId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Canon entity')
      }
      const saved = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      canonEntities.value = [
        ...canonEntities.value.filter((entity) => entity.id !== saved.id),
        saved,
      ].sort((left, right) =>
        `${left.entity_type}:${left.name}`.localeCompare(`${right.entity_type}:${right.name}`)
      )
      if (requestEpoch !== canonSelectionEpoch) return
      const current = { ...canonDraft.value }
      acknowledgeDraftSave(requestScope, snapshot, current)
      if (activeCanonId.value !== saved.id) {
        // Only an actual selection change may bypass its guard.
        suppressNextSelectionGuard = true
        activeCanonId.value = saved.id
        canonDraft.value = current
        discardSavedScope(requestScope, snapshot)
        acknowledgeDraftSave(canonScopeKey(projectId, saved.id), snapshot, current)
      }
      canonStatus.value = 'Canon entity saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      if (!isActiveProject(projectId) || requestEpoch !== canonSelectionEpoch) return
      canonError.value = 'Canon save failed. Check for duplicate names or API errors.'
    } finally {
      isSavingCanon.value = false
    }
  }

  async function deleteCanonEntity() {
    canonError.value = ''
    canonStatus.value = ''
    const projectId = context.activeProjectId
    const entityId = activeCanonId.value

    if (!projectId || !entityId) {
      canonError.value = 'Select a Canon entity first.'
      return
    }

    isDeletingCanon.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/canon/entities/${entityId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Canon entity')
      }
      if (!isActiveProject(projectId)) {
        return
      }
      canonEntities.value = canonEntities.value.filter((entity) => entity.id !== entityId)
      startNewCanonEntity()
      canonStatus.value = 'Canon entity deleted.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      canonError.value = 'Canon delete failed. Check that the API is running.'
    } finally {
      isDeletingCanon.value = false
    }
  }

  /** Drop project-scoped state before the workspace loads another project. */
  function resetProjectState() {
    resetting = true
    canonEntities.value = []
    activeCanonId.value = ''
    canonDraft.value = createEmptyCanonDraft()
    canonError.value = ''
    canonStatus.value = ''
    resetting = false
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [[canonScopeKey(), () => canonDraft.value]]
  }

  return {
    canonEntities,
    activeCanonId,
    canonDraft,
    canonError,
    canonStatus,
    isSavingCanon,
    isDeletingCanon,
    activeCanonEntity,
    canonStateLabel,
    createEmptyCanonDraft,
    canonScopeKey,
    startNewCanonEntity,
    saveCanonEntity,
    deleteCanonEntity,
    resetProjectState,
    draftSnapshotEntries,
  }
})
