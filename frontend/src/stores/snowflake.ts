import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import { useScopedRequest } from '../composables/useScopedRequest'
import { discardSavedScope, queueAutosave } from '../services/draftSessions'
import type {
  SnowflakeStep,
  SnowflakeArtifact,
  WorkflowAgentTrace,
  SnowflakeGenerationResponse,
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
  const artifactDraft = ref('')
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

  const hasUnsavedArtifactChanges = computed(
    () => artifactDraft.value.trim() !== (savedActiveArtifact.value?.content ?? '')
  )

  const artifactStateLabel = computed(() => {
    if (artifactStatus.value) {
      return artifactStatus.value
    }
    if (hasUnsavedArtifactChanges.value) {
      return 'Unsaved changes'
    }
    return savedActiveArtifact.value ? 'Saved state loaded' : 'No saved artifact yet'
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
      const response = await fetchApi(
        `/projects/${projectId}/snowflake/artifacts/${ws().activeStepNumber}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
        }
      )
      if (!response.ok) {
        throw new Error('Could not save artifact')
      }
      const saved = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      upsertArtifact(saved)
      useProjectsStore().advanceActiveProject(saved.step_number)
      artifactDraft.value = saved.content
      discardSavedScope(artifactScopeKey(projectId, saved.step_number), saved.content)
      artifactStatus.value = 'Artifact saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      artifactError.value = 'Artifact save failed. Check that the API is running.'
    } finally {
      isSavingArtifact.value = false
    }
  }

  async function generateArtifact() {
    artifactError.value = ''
    artifactStatus.value = ''
    workflowTrace.value = []
    const projectId = ws().activeProject?.id
    const userInput = artifactDraft.value.trim() || ws().activeProject?.premise.trim()

    if (!projectId || !ws().activeStep || !userInput) {
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
      const response = await fetchApi('/snowflake/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          step_number: ws().activeStepNumber,
          user_input: userInput,
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
      upsertArtifact(generated)
      useProjectsStore().advanceActiveProject(generated.step_number)
      artifactDraft.value = generated.content
      discardSavedScope(artifactScopeKey(projectId, generated.step_number), generated.content)
      workflowTrace.value = generated.workflow_trace
      artifactStatus.value = 'Draft generated and saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch (error) {
      artifactError.value =
        error instanceof Error
          ? `Draft generation failed. ${error.message}`
          : 'Draft generation failed. Check that the API is running.'
    } finally {
      isGeneratingArtifact.value = false
    }
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
        .filter((proposal: SceneProposal) => proposal.status === 'pending_review')
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
        sceneProposals.value = report.proposals
        selectedSceneProposalIds.value = report.proposals
          .filter((proposal) => proposal.status === 'pending_review')
          .map((proposal) => proposal.id)
        const warningCount = report.warnings.length
        const cachedNote = report.cached ? `Cached run v${report.run_version}. ` : ''
        sceneProposalStatus.value =
          cachedNote +
          `Parsed ${report.proposals.length} scene proposal(s)` +
          (warningCount > 0 ? `, ${warningCount} parse warning(s).` : '.')
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
      ? []
      : sceneProposals.value
          .filter(
            (proposal) =>
              proposal.status === 'pending_review' &&
              selectedSceneProposalIds.value.includes(proposal.id)
          )
          .map((proposal) => proposal.id)

    if (!acceptAll && ids.length === 0) {
      sceneProposalError.value = 'Select at least one pending scene proposal.'
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
    artifactDraft.value = ''
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
    artifactDraft,
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
    hasUnsavedArtifactChanges,
    artifactStateLabel,
    artifactScopeKey,
    upsertArtifact,
    saveArtifact,
    generateArtifact,
    loadSceneProposals,
    compileStepArtifact,
    toggleSceneProposalSelection,
    acceptSceneProposalBatch,
    rejectSceneProposal,
    resetProjectState,
    draftSnapshotEntries,
  }
})
