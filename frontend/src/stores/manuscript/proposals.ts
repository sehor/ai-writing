import { computed, ref, type Ref } from 'vue'
import { readErrorDetail } from '../../api/errors'
import { useProposalDraftStore } from '../proposalDraft'
import type { ManuscriptProposal, ManuscriptProposalStatus, ConsistencyReport } from '../../types'
import type { ManuscriptFeedback } from './feedback'
import { useProjectContextStore } from '../projectContext'
import { fetchApi } from '../../api/client'

interface ProposalDependencies {
  activeSceneId: Readonly<Ref<string>>
  loadManuscriptScenes: (projectId: string) => Promise<void>
  refreshCommittedRevision: (projectId: string) => Promise<void>
}

export function useManuscriptProposals(feedback: ManuscriptFeedback, { activeSceneId, loadManuscriptScenes, refreshCommittedRevision }: ProposalDependencies) {
  const context = useProjectContextStore()
  const isActiveProject = (projectId: string) => projectId === context.activeProjectId
  const { manuscriptError, manuscriptStatus } = feedback
  const manuscriptProposals = ref<ManuscriptProposal[]>([])
  const activeProposalId = ref('')
  const isCreatingProposal = ref(false)
  const isCreatingProviderProposal = ref(false)
  const isUpdatingProposal = ref(false)
  const proposalConsistencyReport = ref<ConsistencyReport | null>(null)
  const isCheckingProposalConsistency = ref(false)
  const activeProposal = computed(() =>
    manuscriptProposals.value.find((proposal) => proposal.id === activeProposalId.value)
  )

  const pendingProposalCount = computed(
    () => manuscriptProposals.value.filter((proposal) => proposal.status === 'pending_review').length
  )
  async function loadManuscriptProposals(projectId = context.activeProjectId) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptProposals.value = []
      activeProposalId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/proposals`)
      if (!response.ok) {
        throw new Error('Could not load manuscript proposals')
      }
      const proposals = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptProposals.value = proposals
      if (!manuscriptProposals.value.some((proposal) => proposal.id === activeProposalId.value)) {
        activeProposalId.value = manuscriptProposals.value[0]?.id ?? ''
      }
    } catch {
      manuscriptError.value = '草稿列表加载失败，请刷新重试。'
    }
  }
  async function createProposalFromScene(provider = false) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = context.activeProjectId
    const sceneId = activeSceneId.value

    if (!projectId || !sceneId) {
      manuscriptError.value = '请先选择场景。'
      return
    }

    const loadingFlag = provider ? isCreatingProviderProposal : isCreatingProposal
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/proposals/from-scene/${sceneId}${providerPath}`,
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
        throw new Error(detail.message || 'Could not create manuscript proposal')
      }
      const created: ManuscriptProposal = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptProposals.value = [
        created,
        ...manuscriptProposals.value.filter((proposal) => proposal.id !== created.id),
      ]
      activeProposalId.value = created.id
      manuscriptStatus.value = provider
        ? 'Provider proposal created for review.'
        : 'Proposal created for review.'
    } catch (error) {
      manuscriptError.value =
        error instanceof Error
          ? `Proposal creation failed. ${error.message}`
          : 'Proposal creation failed. Check that the API is running.'
    } finally {
      loadingFlag.value = false
    }
  }

  /** Every committed revision refreshes the same authoring/review surfaces. */
  async function updateProposalStatus(proposalId: string, status: ManuscriptProposalStatus) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = context.activeProjectId

    if (!projectId) {
      manuscriptError.value = '请先创建或选择项目。'
      return
    }

    const draft = useProposalDraftStore()
    if (status === 'accepted' && (draft.projectId !== projectId || draft.proposalId !== proposalId || !draft.title.trim() || !draft.content.trim())) {
      manuscriptError.value = '请打开草稿并填写标题和正文后再接受。'
      return
    }

    isUpdatingProposal.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/proposals/${proposalId}/${status === 'accepted' ? 'accept' : 'status'}`,
        {
          method: status === 'accepted' ? 'POST' : 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(status === 'accepted' ? draft.snapshot() : { status }),
        }
      )
      if (!response.ok) {
        if (response.status === 409 && status === 'accepted') await loadManuscriptScenes(projectId)
        throw new Error((await readErrorDetail(response)).message || 'Could not update manuscript proposal')
      }
      const updated: ManuscriptProposal = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptProposals.value = manuscriptProposals.value.map((proposal) =>
        proposal.id === updated.id ? updated : proposal
      )
      if (status === 'accepted') {
        draft.committed()
        await refreshCommittedRevision(projectId)
        if (!isActiveProject(projectId)) {
          return
        }
      }
      activeProposalId.value = updated.id
      manuscriptStatus.value =
        status === 'accepted'
          ? '草稿已接受，后台分析已安排。'
          : '草稿已拒绝。'
    } catch (error) {
      manuscriptError.value = error instanceof Error ? error.message : 'Proposal update failed. Check that the API is running.'
    } finally {
      isUpdatingProposal.value = false
    }
  }

  async function checkProposalConsistency(proposalId: string) {
    const projectId = context.activeProjectId
    const draft = useProposalDraftStore()
    if (!projectId || draft.proposalId !== proposalId || !draft.title.trim() || !draft.content.trim()) {
      manuscriptError.value = '请先打开并填写待审核草稿。'
      return
    }
    isCheckingProposalConsistency.value = true
    manuscriptError.value = ''
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/proposals/${proposalId}/consistency`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(draft.snapshot()),
        },
      )
      if (!response.ok) throw new Error((await readErrorDetail(response)).message || '一致性检查失败')
      const report: ConsistencyReport = await response.json()
      proposalConsistencyReport.value = report
      manuscriptStatus.value = report.summary.critical_count
        ? `发现 ${report.summary.critical_count} 个阻断问题。`
        : '接受前一致性检查通过。'
    } catch (error) {
      manuscriptError.value = error instanceof Error ? error.message : '一致性检查失败。'
    } finally {
      isCheckingProposalConsistency.value = false
    }
  }

  function resetProposals() {
    manuscriptProposals.value = []
    activeProposalId.value = ''
  }
  function clearProposalConsistencyReport() { proposalConsistencyReport.value = null }

  return {
    manuscriptProposals,
    activeProposalId,
    isCreatingProposal,
    isCreatingProviderProposal,
    isUpdatingProposal,
    proposalConsistencyReport,
    isCheckingProposalConsistency,
    activeProposal,
    pendingProposalCount,
    loadManuscriptProposals,
    createProposalFromScene,
    updateProposalStatus,
    checkProposalConsistency,
    resetProposals,
    clearProposalConsistencyReport,
  }
}
