import { computed, ref, watch } from 'vue'
import { defineStore, storeToRefs } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import { queueAutosave } from '../services/draftSessions'
import type {
  WritebackProposalStatus,
  ReferenceSuggestionStatus,
  WritebackProposal,
  ReferenceSuggestion,
  ReferenceDraft,
  HermesRevisionProcessResponse,
  ConsistencyReport,
} from '../types'
import { useCanonStore } from './canon'
import { useGraphStore } from './graph'
import type { ManuscriptRevisionSource } from './manuscriptReviewPort'
import { useMemoryStore } from './memory'
import { useProjectContextStore } from './projectContext'
import { useAnalysisJobsStore, analysisJobLabel } from './analysisJobs'
import { useNarrativeStore } from './narrative'
import { supportedWriteback } from '../domain/writeback'

/** Human review queues: write-back proposals, reference suggestions, and the
 *  consistency reports / post-acceptance analysis jobs they schedule. */
export const useReviewsStore = defineStore('reviews', () => {
  const analysisJobs = useAnalysisJobsStore()
  const { jobs: postAcceptJobs, error: analysisJobsError } = storeToRefs(analysisJobs)
  const context = useProjectContextStore()
  let revisionSource: ManuscriptRevisionSource = () => []
  function configureRevisionSource(source: ManuscriptRevisionSource) { revisionSource = source }

  // ---- Write-back proposals ----
  const writebackProposals = ref<WritebackProposal[]>([])
  const activeWritebackId = ref('')
  const writebackError = ref('')
  const writebackStatus = ref('')
  const isCreatingWriteback = ref(false)
  const isCreatingProviderWriteback = ref(false)
  const isUpdatingWriteback = ref(false)
  const isProcessingHermesRevision = ref(false)
  const hermesProcessReport = ref<HermesRevisionProcessResponse | null>(null)

  // ---- Reference suggestions ----
  const referenceSuggestions = ref<ReferenceSuggestion[]>([])
  const activeReferenceId = ref('')
  const referenceDraft = ref<ReferenceDraft>(createEmptyReferenceDraft())
  const referenceError = ref('')
  const referenceStatus = ref('')
  const isGeneratingReference = ref(false)
  const isGeneratingProviderReference = ref(false)
  const isUpdatingReference = ref(false)

  // ---- Consistency reports + post-acceptance analysis (P1-07) ----
  const consistencyReport = ref<ConsistencyReport | null>(null)
  const consistencyRevisionId = ref('')
  const consistencyError = ref('')
  const consistencyStatus = ref('')
  const isRunningConsistencyCheck = ref(false)

  const activeWritebackProposal = computed(() =>
    writebackProposals.value.find((proposal) => proposal.id === activeWritebackId.value)
  )

  const pendingWritebackCount = computed(
    () => writebackProposals.value.filter((proposal) => proposal.status === 'pending_review').length
  )

  const activeReferenceSuggestion = computed(() =>
    referenceSuggestions.value.find((suggestion) => suggestion.id === activeReferenceId.value)
  )

  const pendingReferenceCount = computed(
    () => referenceSuggestions.value.filter((suggestion) => suggestion.status === 'pending_review').length
  )

  function createEmptyReferenceDraft(): ReferenceDraft {
    return {
      suggestion_type: 'scene_bridge',
      scope_type: 'scene',
      scope_ref: '',
      author_problem: '',
      desired_output: '',
    }
  }

  function isActiveProject(projectId: string) {
    return projectId === context.activeProjectId
  }

  function referenceScopeKey(projectId = context.activeProjectId): string {
    return `reference:${projectId}:request`
  }

  watch(referenceDraft, () => queueAutosave(referenceScopeKey(), () => referenceDraft.value), {
    deep: true,
  })

  async function loadWritebackProposals(projectId = context.activeProjectId, signal?: AbortSignal) {
    writebackError.value = ''
    if (!projectId) {
      writebackProposals.value = []
      activeWritebackId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/writeback/proposals`, { signal })
      if (!response.ok) {
        throw new Error('Could not load write-back proposals')
      }
      const proposals = await response.json()
      if (signal?.aborted || !isActiveProject(projectId)) {
        return
      }
      writebackProposals.value = proposals
      if (!writebackProposals.value.some((proposal) => proposal.id === activeWritebackId.value)) {
        activeWritebackId.value = writebackProposals.value[0]?.id ?? ''
      }
    } catch {
      if (!signal?.aborted && isActiveProject(projectId)) writebackError.value = 'Write-back proposals could not be loaded.'
    }
  }

  async function loadReferenceSuggestions(projectId = context.activeProjectId) {
    referenceError.value = ''
    if (!projectId) {
      referenceSuggestions.value = []
      activeReferenceId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/references/suggestions`)
      if (!response.ok) {
        throw new Error('Could not load reference suggestions')
      }
      const suggestions = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      referenceSuggestions.value = suggestions
      if (!referenceSuggestions.value.some((suggestion) => suggestion.id === activeReferenceId.value)) {
        activeReferenceId.value = referenceSuggestions.value[0]?.id ?? ''
      }
    } catch {
      referenceError.value = 'Reference suggestions could not be loaded.'
    }
  }

  async function generateReferenceSuggestion(provider = false) {
    referenceError.value = ''
    referenceStatus.value = ''
    const projectId = context.activeProjectId
    const authorProblem = referenceDraft.value.author_problem.trim()

    if (!projectId) {
      referenceError.value = '请先创建或选择项目。'
      return
    }

    if (!authorProblem) {
      referenceError.value = 'Describe the writing problem before generating a reference.'
      return
    }

    const loadingFlag = provider ? isGeneratingProviderReference : isGeneratingReference
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetchApi(
        `/projects/${projectId}/references/suggestions/generate${providerPath}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            suggestion_type: referenceDraft.value.suggestion_type,
            scope_type: referenceDraft.value.scope_type,
            scope_ref: referenceDraft.value.scope_ref.trim(),
            author_problem: authorProblem,
            desired_output: referenceDraft.value.desired_output.trim(),
            ...(provider ? context.modelExecutionOptions() : {}),
          }),
        }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not generate reference suggestion')
      }
      const created: ReferenceSuggestion = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      referenceSuggestions.value = [
        created,
        ...referenceSuggestions.value.filter((suggestion) => suggestion.id !== created.id),
      ]
      activeReferenceId.value = created.id
      referenceStatus.value = provider
        ? 'Provider reference created for review.'
        : 'Reference created for review.'
    } catch (error) {
      referenceError.value =
        error instanceof Error
          ? `Reference generation failed. ${error.message}`
          : 'Reference generation failed. Check that the API is running.'
    } finally {
      loadingFlag.value = false
    }
  }

  async function updateReferenceStatus(
    suggestionId: string,
    status: ReferenceSuggestionStatus,
  ) {
    referenceError.value = ''
    referenceStatus.value = ''
    const projectId = context.activeProjectId

    if (!projectId) {
      referenceError.value = '请先创建或选择项目。'
      return
    }

    isUpdatingReference.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/references/suggestions/${suggestionId}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      )
      if (!response.ok) {
        throw new Error('Could not update reference suggestion')
      }
      const updated: ReferenceSuggestion = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      referenceSuggestions.value = referenceSuggestions.value.map((suggestion) =>
        suggestion.id === updated.id ? updated : suggestion
      )
      activeReferenceId.value = updated.id
      referenceStatus.value =
        status === 'accepted' ? '参考建议已接受。' : '参考建议已拒绝。'
    } catch {
      referenceError.value = 'Reference update failed. Check that the API is running.'
    } finally {
      isUpdatingReference.value = false
    }
  }

  function referenceWarnings(suggestion: ReferenceSuggestion) {
    return [
      ...suggestion.canon_warnings,
      ...suggestion.style_notes,
      ...suggestion.graph_warnings,
    ]
  }

  async function createWritebackFromRevision(revisionId: string, provider = false) {
    writebackError.value = ''
    writebackStatus.value = ''
    const projectId = context.activeProjectId

    if (!projectId) {
      writebackError.value = '请先创建或选择项目。'
      return
    }

    const loadingFlag = provider ? isCreatingProviderWriteback : isCreatingWriteback
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetchApi(
        `/projects/${projectId}/writeback/proposals/from-revision/${revisionId}${providerPath}`,
        provider
          ? {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(context.modelExecutionOptions()),
            }
          : { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not create write-back proposals')
      }
      const created: WritebackProposal[] = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      writebackProposals.value = [
        ...created,
        ...writebackProposals.value.filter(
          (proposal) => !created.some((item) => item.id === proposal.id)
        ),
      ]
      activeWritebackId.value = created[0]?.id ?? activeWritebackId.value
      writebackStatus.value = created.length
        ? `${created.length} write-back proposal${created.length === 1 ? '' : 's'} created.`
        : 'No write-back proposals were created.'
    } catch (error) {
      writebackError.value =
        error instanceof Error
          ? `Write-back generation failed. ${error.message}`
          : 'Write-back generation failed. Check that the API is running.'
    } finally {
      loadingFlag.value = false
    }
  }

  async function processRevisionWithHermes(revisionId: string) {
    writebackError.value = ''
    writebackStatus.value = ''
    hermesProcessReport.value = null
    const projectId = context.activeProjectId

    if (!projectId) {
      writebackError.value = '请先创建或选择项目。'
      return
    }

    isProcessingHermesRevision.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/writeback/proposals/from-revision/${revisionId}/hermes`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not process revision with Hermes')
      }
      const result: HermesRevisionProcessResponse = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      const created = result.writeback_proposals
      writebackProposals.value = [
        ...created,
        ...writebackProposals.value.filter(
          (proposal) => !created.some((item) => item.id === proposal.id)
        ),
      ]
      activeWritebackId.value = created[0]?.id ?? activeWritebackId.value
      hermesProcessReport.value = result
      writebackStatus.value = created.length
        ? `Hermes processed the revision and returned ${created.length} proposal${created.length === 1 ? '' : 's'}.`
        : 'Hermes processed the revision without write-back proposals.'
    } catch (error) {
      writebackError.value =
        error instanceof Error
          ? `Hermes processing failed. ${error.message}`
          : 'Hermes processing failed. Check that the API is running.'
    } finally {
      isProcessingHermesRevision.value = false
    }
  }

  async function runConsistencyCheck(revisionId: string, force = false) {
    consistencyError.value = ''
    consistencyStatus.value = ''
    const projectId = context.activeProjectId

    if (!projectId) {
      consistencyError.value = '请先创建或选择项目。'
      return
    }

    isRunningConsistencyCheck.value = true
    try {
      const forceParam = force ? '?force=true' : ''
      const response = await fetchApi(
        `/projects/${projectId}/analysis/consistency/from-revision/${revisionId}${forceParam}`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not run the consistency check')
      }
      const report: ConsistencyReport = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      consistencyReport.value = report
      consistencyRevisionId.value = revisionId
      const { finding_count, critical_count, warning_count } = report.summary
      if (finding_count === 0) {
        consistencyStatus.value = 'Consistency check passed with no findings.'
      } else {
        consistencyStatus.value =
          `${finding_count} finding${finding_count === 1 ? '' : 's'}` +
          (critical_count ? `, ${critical_count} critical` : '') +
          (warning_count ? `, ${warning_count} warning${warning_count === 1 ? '' : 's'}` : '') +
          (report.cached ? ' (replayed cached run).' : '.')
      }
    } catch (error) {
      consistencyError.value =
        error instanceof Error
          ? `Consistency check failed. ${error.message}`
          : 'Consistency check failed. Check that the API is running.'
    } finally {
      isRunningConsistencyCheck.value = false
    }
  }

  // ---- Post-acceptance analysis (P1-07): show job status, surface results ----

  async function loadPostAcceptAnalysisJobs(projectId = context.activeProjectId) {
    if (!projectId) { analysisJobs.stop(); return }
    await analysisJobs.load(projectId, async (completed, signal) => {
      const refreshes: Promise<void>[] = []
      if (completed.some((job) => job.job_type === 'consistency_analysis')) {
        refreshes.push(showLatestConsistencyReport(projectId, undefined, signal))
      }
      if (completed.some((job) => job.job_type === 'writeback_analysis' || job.job_type === 'clp_extraction')) {
        refreshes.push(loadWritebackProposals(projectId, signal))
      }
      await Promise.all(refreshes)
    })
  }

  async function retryPostAcceptAnalysisJob(jobId: string) {
    await analysisJobs.retry(jobId)
  }

  async function showLatestConsistencyReport(
    projectId = context.activeProjectId,
    revisionId?: string,
    signal?: AbortSignal
  ) {
    if (!projectId) {
      return
    }
    const revisions = revisionSource(projectId)
    const revision = revisionId
      ? revisions.find((item) => item.id === revisionId)
      : revisions[0]
    if (!revision) {
      return
    }

    try {
      const response = await fetchApi(
        `/projects/${projectId}/analysis/consistency/from-revision/${revision.id}`, { signal }
      )
      if (!response.ok) {
        return
      }
      const report: ConsistencyReport = await response.json()
      if (signal?.aborted || !isActiveProject(projectId)) {
        return
      }
      consistencyReport.value = report
      consistencyRevisionId.value = revision.id
    } catch {
      // Advisory panel only; the manual Consistency action reports failures.
    }
  }

  async function updateWritebackStatus(proposalId: string, status: WritebackProposalStatus) {
    writebackError.value = ''
    writebackStatus.value = ''
    const projectId = context.activeProjectId
    const proposal = writebackProposals.value.find((item) => item.id === proposalId)
    if (status === 'accepted' && (!proposal || !supportedWriteback(proposal.target))) {
      writebackError.value = '不支持的提案类型，不能接受。'
      return
    }

    if (!projectId) {
      writebackError.value = '请先创建或选择项目。'
      return
    }

    isUpdatingWriteback.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/writeback/proposals/${proposalId}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      )
      if (!response.ok) {
        let detail = 'Could not update write-back proposal'
        try {
          const body = await response.json()
          if (typeof body?.detail === 'string' && body.detail) {
            detail = body.detail
          }
        } catch {
          // keep the default message
        }
        throw new Error(detail)
      }
      const updated: WritebackProposal = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      writebackProposals.value = writebackProposals.value.map((proposal) =>
        proposal.id === updated.id ? updated : proposal
      )
      activeWritebackId.value = updated.id
      if (status === 'accepted') {
        await Promise.all([
          loadWritebackProposals(projectId),
          useGraphStore().loadGraphAnalysis(projectId),
          refreshCanonAndMemory(projectId),
          useNarrativeStore().load(projectId),
        ])
        if (!isActiveProject(projectId)) {
          return
        }
      }
      writebackStatus.value =
        status === 'accepted'
          ? '变更已接受并应用。'
          : status === 'superseded'
            ? 'Write-back marked as superseded.'
            : '变更已拒绝。'
    } catch (error) {
      writebackError.value =
        error instanceof Error
          ? `Write-back update failed. ${error.message}`
          : 'Write-back update failed. Check for duplicate Canon names or invalid payloads.'
    } finally {
      isUpdatingWriteback.value = false
    }
  }

  /** Re-read canon entities and memory records after an applied write-back. */
  async function refreshCanonAndMemory(projectId = context.activeProjectId) {
    if (!projectId) {
      return
    }
    const [canonResponse, memoryResponse] = await Promise.all([
      fetchApi(`/projects/${projectId}/canon/entities`),
      fetchApi(`/projects/${projectId}/memory/records`),
    ])
    if (!canonResponse.ok || !memoryResponse.ok) {
      throw new Error('Could not refresh Canon and Memory')
    }
    const [canon, memory] = await Promise.all([
      canonResponse.json(),
      memoryResponse.json(),
    ])
    if (!isActiveProject(projectId)) {
      return
    }
    useCanonStore().canonEntities = canon
    useMemoryStore().memoryRecords = memory
  }

  /** Drop project-scoped state before the workspace loads another project. */
  function resetProjectState() {
    writebackProposals.value = []
    activeWritebackId.value = ''
    writebackError.value = ''
    writebackStatus.value = ''
    hermesProcessReport.value = null
    referenceSuggestions.value = []
    activeReferenceId.value = ''
    referenceDraft.value = createEmptyReferenceDraft()
    referenceError.value = ''
    referenceStatus.value = ''
    consistencyReport.value = null
    consistencyRevisionId.value = ''
    consistencyError.value = ''
    consistencyStatus.value = ''
    analysisJobs.stop()
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [[referenceScopeKey(), () => referenceDraft.value]]
  }

  return {
    configureRevisionSource,
    writebackProposals,
    activeWritebackId,
    writebackError,
    writebackStatus,
    isCreatingWriteback,
    isCreatingProviderWriteback,
    isUpdatingWriteback,
    isProcessingHermesRevision,
    hermesProcessReport,
    referenceSuggestions,
    activeReferenceId,
    referenceDraft,
    referenceError,
    referenceStatus,
    isGeneratingReference,
    isGeneratingProviderReference,
    isUpdatingReference,
    consistencyReport,
    consistencyRevisionId,
    consistencyError,
    consistencyStatus,
    isRunningConsistencyCheck,
    postAcceptJobs,
    analysisJobsError,
    activeWritebackProposal,
    pendingWritebackCount,
    activeReferenceSuggestion,
    pendingReferenceCount,
    createEmptyReferenceDraft,
    referenceScopeKey,
    loadWritebackProposals,
    loadReferenceSuggestions,
    generateReferenceSuggestion,
    updateReferenceStatus,
    referenceWarnings,
    createWritebackFromRevision,
    processRevisionWithHermes,
    runConsistencyCheck,
    analysisJobLabel,
    loadPostAcceptAnalysisJobs,
    retryPostAcceptAnalysisJob,
    showLatestConsistencyReport,
    updateWritebackStatus,
    resetProjectState,
    draftSnapshotEntries,
  }
})
