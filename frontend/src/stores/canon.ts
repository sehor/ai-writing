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
import type { CanonDraft, CanonEntity } from '../types'
import { useGraphStore } from './graph'
import { useWorkspaceStore } from './workspace'
import type { WorkspaceShell } from './workspaceShell'

/** Confirmed story facts (the Canon DB) and their editor draft. */
export const useCanonStore = defineStore('canon', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }

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
    return activeCanonEntity.value ? 'Editing Canon entity' : 'New Canon entity'
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
    return projectId === ws().activeProjectId
  }

  function canonScopeKey(
    projectId = ws().activeProjectId,
    id = activeCanonId.value
  ): string {
    return `canon:${projectId}:${id || 'new'}`
  }

  watch(canonDraft, () => queueAutosave(canonScopeKey(), () => canonDraft.value), {
    deep: true,
  })

  watch(activeCanonId, (next, prev) => {
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = canonScopeKey(ws().activeProjectId, prev)
      if (isScopeDirty(previousScope, canonDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Canon 实体编辑' : '新建 Canon 表单')) {
          suppressNextSelectionGuard = true
          activeCanonId.value = prev
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
    })
  })

  function startNewCanonEntity() {
    activeCanonId.value = ''
    canonDraft.value = createEmptyCanonDraft()
    canonStatus.value = ''
    canonError.value = ''
  }

  async function saveCanonEntity() {
    canonError.value = ''
    canonStatus.value = ''
    const projectId = ws().activeProject?.id
    const name = canonDraft.value.name.trim()

    if (!projectId) {
      canonError.value = 'Create or select a project first.'
      return
    }

    if (!name) {
      canonError.value = 'Canon entity name is required.'
      return
    }

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
      const url = activeCanonId.value
        ? `/projects/${projectId}/canon/entities/${activeCanonId.value}`
        : `/projects/${projectId}/canon/entities`
      const response = await fetchApi(url, {
        method: activeCanonId.value ? 'PUT' : 'POST',
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
      clearDraft(canonScopeKey(projectId, activeCanonId.value))
      suppressNextSelectionGuard = true
      activeCanonId.value = saved.id
      canonStatus.value = 'Canon entity saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      canonError.value = 'Canon save failed. Check for duplicate names or API errors.'
    } finally {
      isSavingCanon.value = false
    }
  }

  async function deleteCanonEntity() {
    canonError.value = ''
    canonStatus.value = ''
    const projectId = ws().activeProject?.id
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
    canonEntities.value = []
    activeCanonId.value = ''
    canonDraft.value = createEmptyCanonDraft()
    canonError.value = ''
    canonStatus.value = ''
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
