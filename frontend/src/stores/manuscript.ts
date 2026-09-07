import { defineStore } from 'pinia'
import { useProjectContextStore } from './projectContext'
import type { ManuscriptReviewPort } from './manuscriptReviewPort'
import { useManuscriptFeedback } from './manuscript/feedback'
import { useManuscriptStructure } from './manuscript/structure'
import { useAcceptedScenes } from './manuscript/acceptedScenes'
import { useManuscriptProposals } from './manuscript/proposals'
import { useManuscriptHistory } from './manuscript/history'
import { useManuscriptEditing } from './manuscript/editing'
import { useManuscriptVolumes } from './manuscript/volumes'

/** Compatibility facade and composition root. Each module is created once in this Pinia scope. */
export const useManuscriptStore = defineStore('manuscript', () => {
  const context = useProjectContextStore()
  const feedback = useManuscriptFeedback()
  const structure = useManuscriptStructure()
  const volumes = useManuscriptVolumes()
  const accepted = useAcceptedScenes(feedback)
  const proposals = useManuscriptProposals(feedback, {
    activeSceneId: structure.activeSceneId,
    loadManuscriptScenes: accepted.loadManuscriptScenes,
    refreshCommittedRevision,
  })
  const history = useManuscriptHistory(feedback, {
    refreshCommittedRevision,
    clearProposalConsistencyReport: proposals.clearProposalConsistencyReport,
  })
  const editing = useManuscriptEditing(feedback, {
    manuscriptScenes: accepted.manuscriptScenes,
    refreshCommittedRevision,
    invalidateHistoryOutput: history.invalidateHistoryOutput,
  })

  // An isolated editor has no review panels; the application wires them when mounted.
  let reviewPort: ManuscriptReviewPort | undefined
  function configureReviewPort(port: ManuscriptReviewPort) { reviewPort = port }

  /** Acceptance, restore, and manual save refresh the same authoring/review surfaces. */
  async function refreshCommittedRevision(projectId: string) {
    await Promise.all([
      accepted.loadManuscriptScenes(projectId),
      history.loadManuscriptRevisions(projectId),
      reviewPort?.loadWritebackProposals(projectId),
    ])
    if (projectId !== context.activeProjectId) return
    await Promise.all([
      reviewPort?.loadPostAcceptAnalysisJobs(projectId),
      reviewPort?.showLatestConsistencyReport(projectId),
    ])
  }

  function resetProjectState() {
    editing.cancelEditingManuscriptScene()
    structure.resetStructure()
    volumes.resetVolumes()
    proposals.resetProposals()
    accepted.resetAcceptedScenes()
    history.resetHistory()
    feedback.resetFeedback()
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [
      ...structure.structureDraftSnapshotEntries(),
      ...volumes.volumeDraftSnapshotEntries(),
      [editing.manuscriptEditScopeKey(), editing.currentManuscriptEdits],
    ]
  }

  return {
    ...feedback,
    ...structure,
    ...volumes,
    ...accepted,
    ...proposals,
    ...history,
    ...editing,
    configureReviewPort,
    resetProjectState,
    draftSnapshotEntries,
  }
})
