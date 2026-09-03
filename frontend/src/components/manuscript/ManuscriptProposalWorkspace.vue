<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, watch, onBeforeUnmount } from 'vue'
import { statusText } from '../../utils/format'
import { useManuscriptStore } from '../../stores/manuscript'
import { useReviewsStore } from '../../stores/reviews'
import { useWorkspaceStore } from '../../stores/workspace'
import { useProposalDraftStore } from '../../stores/proposalDraft'
import { confirmLeave } from '../../composables/useDirtyGuard'

const store = useManuscriptStore()
const {
  manuscriptProposals,
  activeProposalId,
  isUpdatingProposal,
  manuscriptError,
  manuscriptStatus,
  activeProposal,
  pendingProposalCount,
  acceptedSceneCount,
  revisionCount,
  proposalConsistencyReport,
  isCheckingProposalConsistency,
} = storeToRefs(store)
const { pendingWritebackCount } = storeToRefs(useReviewsStore())
const { updateProposalStatus, checkProposalConsistency } = store
const workspace = useWorkspaceStore()
const draft = useProposalDraftStore()
const currentScene = computed(() => store.manuscriptScenes.find((scene) => scene.scene_id === activeProposal.value?.scene_id))
const versionConflict = computed(() => draft.expectedSceneVersion !== (currentScene.value?.version ?? 0))
watch(() => [workspace.activeProjectId, activeProposal.value?.id], () => {
  const proposal = activeProposal.value
  if (!proposal || !workspace.activeProjectId || proposal.status !== 'pending_review') return
  if (draft.projectId === workspace.activeProjectId && draft.proposalId !== proposal.id && draft.dirty &&
      !confirmLeave(draft.scopeKey, 'AI 草稿')) {
    activeProposalId.value = draft.proposalId
    return
  }
  const version = store.manuscriptScenes.find((scene) => scene.scene_id === proposal.scene_id)?.version ?? 0
  draft.open(workspace.activeProjectId, proposal, version)
}, { immediate: true })
watch(() => [draft.title, draft.content, activeProposal.value?.id], () => {
  store.proposalConsistencyReport = null
})
onBeforeUnmount(() => draft.persist())
</script>

<template>
  <section class="proposal-workspace">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Review Queue</p>
        <h3>Manuscript Proposals</h3>
      </div>
      <div class="button-row">
        <span class="step-chip">{{ pendingProposalCount }} pending</span>
        <span class="step-chip">{{ acceptedSceneCount }} accepted scenes</span>
        <span class="step-chip">{{ revisionCount }} revisions</span>
        <span class="step-chip">{{ pendingWritebackCount }} write-backs</span>
      </div>
    </div>

    <p v-if="manuscriptError" class="error">{{ manuscriptError }}</p>
    <p v-else-if="manuscriptStatus" class="save-state">{{ manuscriptStatus }}</p>

    <div class="proposal-grid">
      <aside class="proposal-list" aria-label="Manuscript proposals">
        <button
          v-for="proposal in manuscriptProposals"
          :key="proposal.id"
          :class="{ active: proposal.id === activeProposalId }"
          type="button"
          @click="activeProposalId = proposal.id"
        >
          <span>{{ proposal.title }}</span>
          <small>{{ statusText(proposal.status) }}</small>
        </button>
        <p v-if="manuscriptProposals.length === 0" class="empty-state">
          No manuscript proposals yet.
        </p>
      </aside>

      <section v-if="activeProposal" class="proposal-detail">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">{{ statusText(activeProposal.status) }}</p>
            <h4>{{ activeProposal.title }}</h4>
          </div>
          <div class="button-row">
            <button
              v-if="activeProposal.status === 'pending_review'"
              class="secondary"
              type="button"
              :disabled="isCheckingProposalConsistency || !draft.title.trim() || !draft.content.trim()"
              @click="checkProposalConsistency(activeProposal.id)"
            >
              {{ isCheckingProposalConsistency ? '检查中…' : '接受前一致性检查' }}
            </button>
            <button
              v-if="activeProposal.status === 'pending_review'"
              class="secondary danger"
              type="button"
              :disabled="isUpdatingProposal"
              @click="updateProposalStatus(activeProposal.id, 'rejected')"
            >
              Reject
            </button>
            <button
              v-if="activeProposal.status === 'pending_review'"
              class="primary"
              type="button"
              :disabled="isUpdatingProposal || versionConflict || !draft.title.trim() || !draft.content.trim()"
              @click="updateProposalStatus(activeProposal.id, 'accepted')"
            >
              Accept · 保存并分析
            </button>
          </div>
        </div>

        <section v-if="proposalConsistencyReport" class="consistency-preview">
          <p class="eyebrow">Pre-accept Consistency</p>
          <p :class="{ error: proposalConsistencyReport.summary.critical_count > 0 }">
            {{ proposalConsistencyReport.summary.finding_count }} findings ·
            {{ proposalConsistencyReport.summary.critical_count }} critical
          </p>
          <ul v-if="proposalConsistencyReport.findings.length">
            <li v-for="finding in proposalConsistencyReport.findings" :key="finding.id">
              <strong>{{ statusText(finding.severity) }}</strong> · {{ finding.title }}
              <small>{{ finding.manuscript_excerpt }}</small>
            </li>
          </ul>
        </section>

        <section>
          <p class="eyebrow">Proposed Draft</p>
          <template v-if="activeProposal.status === 'pending_review'">
            <section v-if="versionConflict" class="draft-conflict" role="alert">
              <p class="error-text">正式正文已变更：草稿基于 v{{ draft.expectedSceneVersion }}，当前为 v{{ currentScene?.version ?? 0 }}。请核对后再接受。</p>
              <details><summary>查看当前正式正文</summary><pre>{{ currentScene?.content ?? '尚无正式正文' }}</pre></details>
              <button class="secondary" type="button" @click="draft.rebase(currentScene?.version ?? 0)">已核对新版正文，更新草稿基准</button>
            </section>
            <label><span>草稿标题</span><input v-model="draft.title" aria-label="AI 草稿标题" maxlength="160" :disabled="isUpdatingProposal" /></label>
            <label><span>作者草稿 · 可编辑后再接受</span><textarea v-model="draft.content" data-testid="proposal-draft-content" aria-label="AI 草稿正文" rows="18" maxlength="40000" :disabled="isUpdatingProposal" /></label>
            <p class="save-state">{{ draft.dirty ? '有未提交修改 · 自动保存为本地草稿' : '尚未修改 AI 原稿' }}<span v-if="draft.restored"> · 已恢复本地草稿</span></p>
            <details><summary>AI 原稿与修改稿对照</summary><div class="draft-comparison"><section><h5>AI 原稿（只读）</h5><pre>{{ activeProposal.content }}</pre></section><section><h5>作者修改</h5><pre>{{ draft.content }}</pre></section></div></details>
          </template>
          <template v-else><p class="eyebrow">AI 原稿（只读）· 正式正文见 Accepted Manuscript</p><pre>{{ activeProposal.content }}</pre></template>
        </section>
        <section>
          <p class="eyebrow">Review Checklist</p>
          <ul>
            <li v-for="item in activeProposal.checklist" :key="item">{{ item }}</li>
          </ul>
        </section>
        <details>
          <summary>Source Context · 展开核对生成依据</summary>
          <pre>{{ activeProposal.context }}</pre>
        </details>
      </section>
    </div>
  </section>
</template>
