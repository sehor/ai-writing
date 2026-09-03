import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import { useScopedRequest } from '../composables/useScopedRequest'
import { discardSavedScope, queueAutosave } from '../services/draftSessions'
import type {
  SnowflakeStep,
  SnowflakeArtifact,
  SnowflakeArtifactRevision,
  SnowflakeRevisionDecisionResponse,
  SnowflakeRevisionPage,
  SnowflakeStepState,
  WorkflowAgentTrace,
  SnowflakeGenerationResponse,
  SnowflakeManuscriptProgress,
  SnowflakeRecordRevision,
  SnowflakeRecordPage,
  CanonExtractionReport,
  SceneParseReport,
  SceneProposal,
  SceneProposalAcceptanceReport,
} from '../types'
import { useGraphStore } from './graph'
import { useManuscriptStore } from './manuscript'
import { useProjectsStore } from './projects'
import { useReviewsStore } from './reviews'
import { useWorkspaceStore } from './workspace'
import type { WorkspaceShell } from './workspaceShell'

/** Snowflake method steps, artifact editor/generation, and the structured
 *  Step 7/8 compiler that produces canon / scene proposals. */
export const useSnowflakeStore = defineStore('snowflake', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }
  const requestScopes = useScopedRequest()

  const steps = ref<SnowflakeStep[]>([])
  const artifacts = ref<SnowflakeArtifact[]>([])
  const stepStates = ref<SnowflakeStepState[]>([])
  const revisions = ref<SnowflakeArtifactRevision[]>([])
  const activeRevisionId = ref('')
  const artifactDraft = ref('')
  const generationInstruction = ref('')
  const manuscriptProgress = ref<SnowflakeManuscriptProgress | null>(null)
  const records = ref<SnowflakeRecordRevision[]>([])
  const recordPage = ref(1)
  const recordTotalPages = ref(0)
  const workflowTrace = ref<WorkflowAgentTrace[]>([])
  const artifactError = ref('')
  const artifactStatus = ref('')
  const isSavingArtifact = ref(false)
  const isGeneratingArtifact = ref(false)
  const isCompilingArtifact = ref(false)
  const sceneProposals = ref<SceneProposal[]>([])
  const canonExtractionReport = ref<CanonExtractionReport | null>(null)
  const sceneParseReport = ref<SceneParseReport | null>(null)
  const selectedSceneProposalIds = ref<string[]>([])
  const sceneProposalError = ref('')
  const sceneProposalStatus = ref('')

  const savedActiveArtifact = computed(() =>
    artifacts.value.find((artifact) => artifact.step_number === ws().activeStepNumber)
  )

  const activeStepState = computed(() =>
    stepStates.value.find((state) => state.step.number === ws().activeStepNumber)
  )

  const activeRevision = computed(() =>
    revisions.value.find((revision) => revision.id === activeRevisionId.value)
  )

  const editorBaselineContent = computed(
    () => activeRevision.value?.content ?? savedActiveArtifact.value?.content ?? ''
  )

  const hasUnsavedArtifactChanges = computed(
    () => artifactDraft.value.trim() !== editorBaselineContent.value.trim()
  )

  const artifactStateLabel = computed(() => {
    if (artifactStatus.value) {
      return artifactStatus.value
    }
    if (hasUnsavedArtifactChanges.value) {
      return 'Unsaved changes'
    }
    if (activeRevision.value?.status === 'draft') return 'Draft saved — not approved'
    if (activeRevision.value?.status === 'pending_review') return 'Pending human review'
    if (activeStepState.value?.state === 'stale') return 'Needs review — upstream changed'
    if (activeStepState.value?.state === 'approved') return 'Approved revision loaded'
    if (activeStepState.value?.state === 'skipped') return 'Optional step skipped'
    return 'No approved revision yet'
  })

  function isActiveProject(projectId: string) {
    return projectId === ws().activeProjectId
  }

  function artifactScopeKey(
    projectId = ws().activeProjectId,
    step = ws().activeStepNumber
  ): string {
    return `snowflake:${projectId}:${step}`
  }

  watch(artifactDraft, () => queueAutosave(artifactScopeKey(), () => artifactDraft.value))

  function upsertArtifact(artifact: SnowflakeArtifact) {
    artifacts.value = [
      ...artifacts.value.filter((item) => item.step_number !== artifact.step_number),
      artifact,
    ].sort((left, right) => left.step_number - right.step_number)
  }

  function upsertRevision(revision: SnowflakeArtifactRevision) {
    revisions.value = [
      revision,
      ...revisions.value.filter((item) => item.id !== revision.id),
    ].sort((left, right) => right.revision_no - left.revision_no)
  }

  async function loadStepStates(projectId = ws().activeProject?.id) {
    if (!projectId) {
      stepStates.value = []
      return
    }
    const response = await fetchApi(`/projects/${projectId}/snowflake/steps`)
    if (!response.ok) throw new Error('Could not load Snowflake step states')
    const loaded: SnowflakeStepState[] = await response.json()
    if (isActiveProject(projectId)) stepStates.value = loaded
  }

  async function loadRevisions(
    stepNumber = ws().activeStepNumber,
    projectId = ws().activeProject?.id
  ) {
    if (!projectId) {
      revisions.value = []
      activeRevisionId.value = ''
      return
    }
    const response = await fetchApi(
      `/projects/${projectId}/snowflake/artifacts/${stepNumber}/revisions?page=1&page_size=100`
    )
    if (!response.ok) throw new Error('Could not load Snowflake revision history')
    const page: SnowflakeRevisionPage = await response.json()
    if (!isActiveProject(projectId) || stepNumber !== ws().activeStepNumber) return
    revisions.value = page.data
    activeRevisionId.value = ''
  }

  async function loadManuscriptProgress(projectId = ws().activeProject?.id) {
    if (!projectId) {
      manuscriptProgress.value = null
      return
    }
    const response = await fetchApi(`/projects/${projectId}/snowflake/manuscript-progress`)
    if (!response.ok) throw new Error('Could not load Manuscript progress')
    const loaded: SnowflakeManuscriptProgress = await response.json()
    if (isActiveProject(projectId)) manuscriptProgress.value = loaded
  }

  async function loadRecords(stepNumber = ws().activeStepNumber, page = 1) {
    const projectId = ws().activeProject?.id
    if (!projectId || stepNumber < 6 || stepNumber > 9) {
      records.value = []
      return
    }
    const response = await fetchApi(
      `/projects/${projectId}/snowflake/steps/${stepNumber}/records?page=${page}&page_size=50`
    )
    if (!response.ok) throw new Error('Could not load Snowflake records')
    const loaded: SnowflakeRecordPage = await response.json()
    if (!isActiveProject(projectId) || ws().activeStepNumber !== stepNumber) return
    records.value = loaded.data
    recordPage.value = loaded.page
    recordTotalPages.value = loaded.total_pages
  }

  async function createRecordRevision(recordId: string, position: number, payload: Record<string, unknown>) {
    const projectId = ws().activeProject?.id
    const stepNumber = ws().activeStepNumber
    if (!projectId || stepNumber < 6 || stepNumber > 9) return
    const current = records.value.find((record) => record.record_id === recordId)
    const baseRevisionId = current?.status === 'accepted' ? current.id : current?.base_revision_id ?? ''
    const response = await fetchApi(`/projects/${projectId}/snowflake/record-revisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        step_number: stepNumber,
        record_id: recordId,
        position,
        payload,
        base_revision_id: baseRevisionId,
      }),
    })
    if (!response.ok) throw new Error((await readErrorDetail(response)).message || 'Could not save record revision')
    await loadRecords(stepNumber, recordPage.value)
  }

  async function decideRecordRevision(revision: SnowflakeRecordRevision, decision: 'accepted' | 'rejected') {
    const projectId = ws().activeProject?.id
    if (!projectId) return
    const response = await fetchApi(
      `/projects/${projectId}/snowflake/record-revisions/${revision.id}/decisions`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          expected_revision_id: revision.base_revision_id,
        }),
      },
    )
    if (!response.ok) throw new Error((await readErrorDetail(response)).message || 'Could not review record revision')
    await loadRecords(revision.step_number, recordPage.value)
  }

  function openRevision(revisionId: string) {
    const revision = revisions.value.find((item) => item.id === revisionId)
    if (!revision) return
    activeRevisionId.value = revisionId
    artifactDraft.value = revision.content
    artifactStatus.value = `Revision ${revision.revision_no} · ${revision.status}`
  }

  async function saveArtifact() {
    artifactError.value = ''
    artifactStatus.value = ''
    const projectId = ws().activeProject?.id
    const content = artifactDraft.value.trim()

    if (!projectId || !ws().activeStep) {
      artifactError.value = 'Create or select a project first.'
      return
    }

    if (!content) {
      artifactError.value = 'Artifact content is required before saving.'
      return
    }

    isSavingArtifact.value = true
    try {
      const editing = activeRevision.value
      const canPatch = editing?.status === 'draft' && editing.source === 'human'
      const response = await fetchApi(
        canPatch
          ? `/projects/${projectId}/snowflake/artifact-revisions/${editing.id}`
          : `/projects/${projectId}/snowflake/artifact-revisions`,
        {
          method: canPatch ? 'PATCH' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            canPatch
              ? { content }
              : {
                  step_number: ws().activeStepNumber,
                  content,
                  parent_revision_id:
                    activeStepState.value?.accepted_revision?.id ?? '',
                  base_head_revision_id:
                    activeStepState.value?.accepted_revision?.id ?? '',
                  source: 'human',
                }
          ),
        }
      )
      if (!response.ok) {
        throw new Error('Could not save artifact')
      }
      const saved: SnowflakeArtifactRevision = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      upsertRevision(saved)
      activeRevisionId.value = saved.id
      artifactDraft.value = saved.content
      discardSavedScope(artifactScopeKey(projectId, saved.step_number), saved.content)
      artifactStatus.value = 'Draft saved. Accept it to update the approved step.'
      await loadStepStates(projectId)
    } catch (error) {
      artifactError.value =
        error instanceof Error ? error.message : 'Artifact draft save failed.'
    } finally {
      isSavingArtifact.value = false
    }
  }

  async function generateArtifact() {
    artifactError.value = ''
    artifactStatus.value = ''
    workflowTrace.value = []
    const projectId = ws().activeProject?.id
    const instruction = generationInstruction.value.trim() || ws().activeProject?.premise.trim()

    if (!projectId || !ws().activeStep || !instruction) {
      artifactError.value = 'Create or select a project first.'
      return
    }

    isGeneratingArtifact.value = true
    // Bind the generation to project + step so a late response can never
    // overwrite a different step's editor (P0-06).
    const generationScope = requestScopes.begin(
      projectId,
      'snowflake',
      String(ws().activeStepNumber)
    )
    try {
      const response = await fetchApi(`/projects/${projectId}/snowflake/generations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          step_number: ws().activeStepNumber,
          instruction,
          base_revision_id: activeStepState.value?.accepted_revision?.id ?? '',
          generation_mode: 'replace',
        }),
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        if (!isActiveProject(projectId) || !requestScopes.isCurrent(generationScope)) {
          return
        }
        if (detail.workflow_trace) {
          workflowTrace.value = detail.workflow_trace
        }
        throw new Error(detail.message || 'Could not generate artifact')
      }
      const generated: SnowflakeGenerationResponse = await response.json()
      if (!isActiveProject(projectId) || !requestScopes.isCurrent(generationScope)) {
        return
      }
      if (!generated.revision) throw new Error('Generation did not return a review revision')
      upsertRevision(generated.revision)
      activeRevisionId.value = generated.revision.id
      artifactDraft.value = generated.content
      discardSavedScope(artifactScopeKey(projectId, generated.step_number), generated.content)
      workflowTrace.value = generated.workflow_trace
      artifactStatus.value = 'AI proposal generated — review and accept or reject it.'
      await loadStepStates(projectId)
    } catch (error) {
      artifactError.value =
        error instanceof Error
          ? `Draft generation failed. ${error.message}`
          : 'Draft generation failed. Check that the API is running.'
    } finally {
      isGeneratingArtifact.value = false
    }
  }

  async function decideRevision(revisionId: string, decision: 'accepted' | 'rejected') {
    artifactError.value = ''
    artifactStatus.value = ''
    const projectId = ws().activeProject?.id
    const state = activeStepState.value
    if (!projectId || !state) return
    isSavingArtifact.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/snowflake/artifact-revisions/${revisionId}/decisions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            decision,
            expected_head_revision_id: state.accepted_revision?.id ?? '',
          }),
        }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || `Could not ${decision === 'accepted' ? 'accept' : 'reject'} revision`)
      }
      const result: SnowflakeRevisionDecisionResponse = await response.json()
      upsertRevision(result.revision)
      await loadStepStates(projectId)
      if (decision === 'accepted') {
        upsertArtifact({
          project_id: projectId,
          step_number: result.revision.step_number,
          artifact: result.revision.artifact_type,
          content: result.revision.content,
        })
        useProjectsStore().advanceActiveProject(result.revision.step_number)
        activeRevisionId.value = ''
        artifactDraft.value = result.revision.content
        discardSavedScope(
          artifactScopeKey(projectId, result.revision.step_number),
          result.revision.content
        )
        artifactStatus.value = result.affected_steps.length
          ? `Revision approved. Steps ${result.affected_steps.join(', ')} now need review.`
          : 'Revision approved.'
        await useGraphStore().loadGraphAnalysis(projectId)
      } else {
        activeRevisionId.value = ''
        artifactDraft.value = state.accepted_revision?.content ?? ''
        artifactStatus.value = 'Revision rejected. Approved content is unchanged.'
      }
    } catch (error) {
      artifactError.value = error instanceof Error ? error.message : 'Revision decision failed.'
      await loadStepStates(projectId).catch(() => undefined)
    } finally {
      isSavingArtifact.value = false
    }
  }

  async function skipActiveStep() {
    const projectId = ws().activeProject?.id
    if (!projectId || !ws().activeStep?.optional) return
    const response = await fetchApi(
      `/projects/${projectId}/snowflake/steps/${ws().activeStepNumber}/skip-decisions`,
      { method: 'POST' }
    )
    if (!response.ok) {
      const detail = await readErrorDetail(response)
      artifactError.value = detail.message || 'Could not skip optional step.'
      return
    }
    await loadStepStates(projectId)
    useProjectsStore().advanceActiveProject(ws().activeStepNumber)
    artifactStatus.value = 'Optional step skipped.'
  }

  // ---- Structured Snowflake compiler (P1-05): Step 7/8 -> proposals ----

  async function loadSceneProposals(projectId = ws().activeProject?.id) {
    sceneProposalError.value = ''
    if (!projectId) {
      sceneProposals.value = []
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/snowflake/scene-proposals`)
      if (!response.ok) {
        throw new Error('Could not load scene proposals')
      }
      const loaded = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      sceneProposals.value = loaded
      selectedSceneProposalIds.value = loaded
        .filter(
          (proposal: SceneProposal) =>
            proposal.status === 'pending_review' && proposal.blocking_errors.length === 0
        )
        .map((proposal: SceneProposal) => proposal.id)
    } catch {
      if (isActiveProject(projectId)) {
        sceneProposalError.value = 'Scene proposals could not be loaded.'
      }
    }
  }

  async function compileStepArtifact() {
    artifactError.value = ''
    artifactStatus.value = ''
    sceneProposalError.value = ''
    sceneProposalStatus.value = ''
    const projectId = ws().activeProject?.id
    const step = ws().activeStepNumber

    if (!projectId || !ws().activeStep) {
      sceneProposalError.value = 'Create or select a project first.'
      return
    }
    if (step !== 7 && step !== 8) {
      return
    }

    isCompilingArtifact.value = true
    try {
      const action = step === 7 ? 'compile-canon-proposals' : 'parse-scene-proposals'
      const response = await fetchApi(
        `/projects/${projectId}/snowflake/artifacts/${step}/${action}`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Compile failed')
      }
      if (!isActiveProject(projectId)) {
        return
      }

      if (step === 7) {
        const report: CanonExtractionReport = await response.json()
        canonExtractionReport.value = report
        await useReviewsStore().loadWritebackProposals(projectId)
        const updateCount = report.proposals.filter(
          (proposal) => proposal.action === 'update'
        ).length
        const cachedNote = report.cached ? `Cached run v${report.run_version}. ` : ''
        sceneProposalStatus.value =
          cachedNote +
          `Extracted ${report.proposals.length} Canon proposal(s) ` +
          `(${report.proposals.length - updateCount} create, ${updateCount} update). ` +
          'Review them in Manuscript > Write-backs before anything touches Canon.'
      } else {
        const report: SceneParseReport = await response.json()
        sceneParseReport.value = report
        await useReviewsStore().loadWritebackProposals(projectId)
        sceneProposals.value = report.proposals
        selectedSceneProposalIds.value = report.proposals
          .filter(
            (proposal) =>
              proposal.status === 'pending_review' && proposal.blocking_errors.length === 0
          )
          .map((proposal) => proposal.id)
        const warningCount = report.warnings.length
        const cachedNote = report.cached ? `Cached run v${report.run_version}. ` : ''
        sceneProposalStatus.value =
          cachedNote +
          `Parsed ${report.proposals.length} scene proposal(s)` +
          (warningCount > 0 ? `, ${warningCount} parse warning(s).` : '.') +
          (report.thread_proposals.length
            ? ` ${report.thread_proposals.length} StoryThread/Event proposal(s) are waiting in Manuscript > Write-backs.`
            : '')
      }
    } catch (error) {
      sceneProposalError.value =
        error instanceof Error
          ? `Compile failed. ${error.message}`
          : 'Compile failed. Check that the API is running.'
    } finally {
      isCompilingArtifact.value = false
    }
  }

  function toggleSceneProposalSelection(proposalId: string) {
    const current = selectedSceneProposalIds.value
    selectedSceneProposalIds.value = current.includes(proposalId)
      ? current.filter((id) => id !== proposalId)
      : [...current, proposalId]
  }

  async function acceptSceneProposalBatch(acceptAll: boolean) {
    sceneProposalError.value = ''
    sceneProposalStatus.value = ''
    const projectId = ws().activeProject?.id
    if (!projectId) {
      sceneProposalError.value = 'Create or select a project first.'
      return
    }

    const ids = acceptAll
      ? sceneProposals.value
          .filter(
            (proposal) =>
              proposal.status === 'pending_review' && proposal.blocking_errors.length === 0
          )
          .map((proposal) => proposal.id)
      : sceneProposals.value
          .filter(
            (proposal) =>
              proposal.status === 'pending_review' &&
              proposal.blocking_errors.length === 0 &&
              selectedSceneProposalIds.value.includes(proposal.id)
          )
          .map((proposal) => proposal.id)

    if (ids.length === 0) {
      sceneProposalError.value = 'Select at least one unblocked pending scene proposal.'
      return
    }

    isCompilingArtifact.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/snowflake/scene-proposals/accept`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ proposal_ids: ids }),
        }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Batch acceptance failed')
      }
      const report: SceneProposalAcceptanceReport = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      await loadSceneProposals(projectId)
      await useManuscriptStore().refreshSceneContracts(projectId)
      sceneProposalStatus.value = `Created ${report.scenes.length} scene contract(s) from parsed proposals.`
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch (error) {
      sceneProposalError.value =
        error instanceof Error
          ? error.message
          : 'Batch acceptance failed. Check that the API is running.'
    } finally {
      isCompilingArtifact.value = false
    }
  }

  async function rejectSceneProposal(proposalId: string) {
    sceneProposalError.value = ''
    sceneProposalStatus.value = ''
    const projectId = ws().activeProject?.id
    if (!projectId) {
      sceneProposalError.value = 'Create or select a project first.'
      return
    }

    isCompilingArtifact.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/snowflake/scene-proposals/${proposalId}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'rejected' }),
        }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not reject the proposal')
      }
      const updated: SceneProposal = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      sceneProposals.value = sceneProposals.value.map((proposal) =>
        proposal.id === updated.id ? updated : proposal
      )
      selectedSceneProposalIds.value = selectedSceneProposalIds.value.filter(
        (id) => id !== proposalId
      )
      sceneProposalStatus.value = `Scene proposal ${updated.sequence} rejected.`
    } catch (error) {
      sceneProposalError.value =
        error instanceof Error ? error.message : 'Reject failed. Check that the API is running.'
    } finally {
      isCompilingArtifact.value = false
    }
  }

  /** Drop project-scoped state before the workspace loads another project. */
  function resetProjectState() {
    artifactError.value = ''
    artifactStatus.value = ''
    workflowTrace.value = []
    artifacts.value = []
    stepStates.value = []
    revisions.value = []
    activeRevisionId.value = ''
    artifactDraft.value = ''
    generationInstruction.value = ''
    manuscriptProgress.value = null
    records.value = []
    recordPage.value = 1
    recordTotalPages.value = 0
    sceneProposals.value = []
    canonExtractionReport.value = null
    sceneParseReport.value = null
    selectedSceneProposalIds.value = []
    sceneProposalError.value = ''
    sceneProposalStatus.value = ''
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [[artifactScopeKey(), () => artifactDraft.value]]
  }

  return {
    steps,
    artifacts,
    stepStates,
    revisions,
    activeRevisionId,
    artifactDraft,
    generationInstruction,
    manuscriptProgress,
    records,
    recordPage,
    recordTotalPages,
    workflowTrace,
    artifactError,
    artifactStatus,
    isSavingArtifact,
    isGeneratingArtifact,
    isCompilingArtifact,
    sceneProposals,
    canonExtractionReport,
    sceneParseReport,
    selectedSceneProposalIds,
    sceneProposalError,
    sceneProposalStatus,
    savedActiveArtifact,
    activeStepState,
    activeRevision,
    editorBaselineContent,
    hasUnsavedArtifactChanges,
    artifactStateLabel,
    artifactScopeKey,
    upsertArtifact,
    upsertRevision,
    loadStepStates,
    loadRevisions,
    loadManuscriptProgress,
    loadRecords,
    createRecordRevision,
    decideRecordRevision,
    openRevision,
    saveArtifact,
    generateArtifact,
    decideRevision,
    skipActiveStep,
    loadSceneProposals,
    compileStepArtifact,
    toggleSceneProposalSelection,
    acceptSceneProposalBatch,
    rejectSceneProposal,
    resetProjectState,
    draftSnapshotEntries,
  }
})
