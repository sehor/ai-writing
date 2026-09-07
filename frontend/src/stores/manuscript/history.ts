import { computed, ref } from 'vue'
import type { ManuscriptRevision, ManuscriptRevisionDiff, ManuscriptExport } from '../../types'
import type { ManuscriptFeedback } from './feedback'
import { useProjectContextStore } from '../projectContext'
import { fetchApi } from '../../api/client'

interface HistoryDependencies {
  refreshCommittedRevision: (projectId: string) => Promise<void>
  clearProposalConsistencyReport: () => void
}

export function useManuscriptHistory(feedback: ManuscriptFeedback, { refreshCommittedRevision, clearProposalConsistencyReport }: HistoryDependencies) {
  const context = useProjectContextStore()
  const isActiveProject = (projectId: string) => projectId === context.activeProjectId
  const { manuscriptError, manuscriptStatus } = feedback
  const manuscriptRevisions = ref<ManuscriptRevision[]>([])
  const revisionDiff = ref<ManuscriptRevisionDiff | null>(null)
  const diffLeftRevisionId = ref('')
  const diffRightRevisionId = ref('')
  const isLoadingDiff = ref(false)
  const isRestoringRevision = ref(false)
  const manuscriptExport = ref<ManuscriptExport | null>(null)
  const isExportingManuscript = ref(false)
  const revisionCount = computed(() => manuscriptRevisions.value.length)
  async function loadManuscriptRevisions(projectId = context.activeProjectId) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptRevisions.value = []
      revisionDiff.value = null
      diffLeftRevisionId.value = ''
      diffRightRevisionId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/revisions`)
      if (!response.ok) {
        throw new Error('Could not load manuscript revisions')
      }
      const revisions = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptRevisions.value = revisions
      syncRevisionCompareSelection()
    } catch {
      manuscriptError.value = 'Manuscript revision history could not be loaded.'
    }
  }

  function syncRevisionCompareSelection() {
    const revisions = manuscriptRevisions.value
    if (revisions.length === 0) {
      diffLeftRevisionId.value = ''
      diffRightRevisionId.value = ''
      revisionDiff.value = null
      return
    }
    if (!revisions.some((revision) => revision.id === diffRightRevisionId.value)) {
      diffRightRevisionId.value = revisions[0].id
    }
    if (!revisions.some((revision) => revision.id === diffLeftRevisionId.value)) {
      diffLeftRevisionId.value = revisions[1]?.id ?? revisions[0].id
    }
  }
  async function loadRevisionDiff() {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    clearProposalConsistencyReport()
    revisionDiff.value = null
    const projectId = context.activeProjectId

    if (!projectId || !diffLeftRevisionId.value || !diffRightRevisionId.value) {
      manuscriptError.value = 'Select two revisions to compare.'
      return
    }

    isLoadingDiff.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/revisions/${diffLeftRevisionId.value}/diff/${diffRightRevisionId.value}`
      )
      if (!response.ok) {
        throw new Error('Could not load revision diff')
      }
      const diff = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      revisionDiff.value = diff
      manuscriptStatus.value = 'Revision diff loaded.'
    } catch {
      manuscriptError.value = 'Revision diff failed. Check that the API is running.'
    } finally {
      isLoadingDiff.value = false
    }
  }

  async function restoreRevision(revisionId: string) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = context.activeProjectId

    if (!projectId) {
      manuscriptError.value = '请先创建或选择项目。'
      return
    }

    isRestoringRevision.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/revisions/${revisionId}/restore`,
        { method: 'POST' }
      )
      if (!response.ok) {
        throw new Error('Could not restore revision')
      }
      if (!isActiveProject(projectId)) {
        return
      }
      await refreshCommittedRevision(projectId)
      if (!isActiveProject(projectId)) {
        return
      }
      revisionDiff.value = null
      manuscriptStatus.value = 'Revision restored as a new current version.'
    } catch {
      manuscriptError.value = 'Revision restore failed. Check that the API is running.'
    } finally {
      isRestoringRevision.value = false
    }
  }

  async function exportManuscript() {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    manuscriptExport.value = null
    const projectId = context.activeProjectId

    if (!projectId) {
      manuscriptError.value = '请先创建或选择项目。'
      return
    }

    isExportingManuscript.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/export`)
      if (!response.ok) {
        throw new Error('Could not export manuscript')
      }
      const exported = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptExport.value = exported
      manuscriptStatus.value = 'Manuscript export generated.'
    } catch {
      manuscriptError.value = 'Manuscript export failed. Check that the API is running.'
    } finally {
      isExportingManuscript.value = false
    }
  }
  function revisionLabel(revision: ManuscriptRevision) {
    return `${revision.title} v${revision.version}`
  }

  function invalidateHistoryOutput() {
    manuscriptExport.value = null
    revisionDiff.value = null
  }
  function resetHistory() {
    manuscriptRevisions.value = []
    diffLeftRevisionId.value = ''
    diffRightRevisionId.value = ''
    invalidateHistoryOutput()
  }

  return {
    manuscriptRevisions,
    revisionDiff,
    diffLeftRevisionId,
    diffRightRevisionId,
    isLoadingDiff,
    isRestoringRevision,
    manuscriptExport,
    isExportingManuscript,
    revisionCount,
    loadManuscriptRevisions,
    syncRevisionCompareSelection,
    loadRevisionDiff,
    restoreRevision,
    exportManuscript,
    revisionLabel,
    invalidateHistoryOutput,
    resetHistory,
  }
}
