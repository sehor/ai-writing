<script setup lang="ts">
import { computed } from 'vue'
import SceneProposalChanges from './SceneProposalChanges.vue'
import { storeToRefs } from 'pinia'
import { useSnowflakeStore } from '../../stores/snowflake'
import { useProjectContextStore } from '../../stores/projectContext'

const snowflake = useSnowflakeStore()
const { activeStepNumber } = storeToRefs(useProjectContextStore())

defineProps<{ hasProject: boolean }>()
const {
  isCompilingArtifact, activeStepState, sceneProposals, canonExtractionReport,
  sceneParseReport, selectedSceneProposalIds, sceneProposalError, sceneProposalStatus,
} = storeToRefs(snowflake)
const { compileStepArtifact, toggleSceneProposalSelection, acceptSceneProposalBatch, rejectSceneProposal } = snowflake
const compilerStep = computed(() => activeStepNumber.value === 7 ? 'canon' : activeStepNumber.value === 8 ? 'scene' : null)
const canonCreateCount = computed(
  () => canonExtractionReport.value?.proposals.filter((proposal) => proposal.action === 'create').length ?? 0
)
const canonUpdateCount = computed(
  () => canonExtractionReport.value?.proposals.filter((proposal) => proposal.action === 'update').length ?? 0
)

function statusLabel(status: string): string {
  if (status === 'pending_review') return 'Pending review'
  if (status === 'accepted') return 'Accepted'
  if (status === 'rejected') return 'Rejected'
  return 'Superseded'
}
</script>

<template>
<section
  v-if="compilerStep"
  class="compile-panel"
  aria-labelledby="compile-panel-title"
>
  <div class="panel-header">
    <div>
      <h3 id="compile-panel-title">
        {{
          compilerStep === 'canon'
            ? '第七步：生成设定建议'
            : '第八步：解析场景建议'
        }}
      </h3>
    </div>
    <span v-if="compilerStep === 'canon' && canonExtractionReport" class="step-chip">
      {{ canonExtractionReport.cached ? 'cached' : 'run' }} v{{ canonExtractionReport.run_version }}
    </span>
    <span v-else-if="compilerStep === 'scene' && sceneParseReport" class="step-chip">
      {{ sceneParseReport.cached ? 'cached' : 'run' }} v{{ sceneParseReport.run_version }}
    </span>
  </div>

  <p class="compile-hint">
    {{
      compilerStep === 'canon'
        ? '将已接受的人物档案编译为设定建议。草稿和已拒绝记录不参与，逐项接受后才写入故事设定。'
        : '将已接受的场景清单解析为场景契约建议。草稿和已拒绝记录不参与；存在阻断问题时暂停编译。'
    }}
  </p>

  <div class="form-actions artifact-actions">
    <p v-if="sceneProposalError" class="error">{{ sceneProposalError }}</p>
    <p v-else-if="sceneProposalStatus" class="save-state">{{ sceneProposalStatus }}</p>
    <div class="button-row">
      <button
        class="primary"
        type="button"
        :disabled="
          isCompilingArtifact ||
          !hasProject ||
          activeStepState?.state !== 'approved'
        "
        @click="compileStepArtifact"
      >
        {{
          isCompilingArtifact
            ? '编译中…'
            : compilerStep === 'canon'
              ? '提取设定建议'
              : '解析场景建议'
        }}
      </button>
    </div>
  </div>

  <template v-if="compilerStep === 'canon' && canonExtractionReport">
    <p v-if="canonExtractionReport.proposals.length" class="compile-summary">
      {{ canonExtractionReport.proposals.length }} proposal(s):
      {{ canonCreateCount }} create, {{ canonUpdateCount }} update.
      Review and accept them under Manuscript &gt; Write-backs.
    </p>
    <p v-else class="save-state">没有新的设定建议，现有设定可能已与记录一致。</p>
    <ul v-if="canonExtractionReport.warnings.length" class="warning-list">
      <li v-for="(warning, index) in canonExtractionReport.warnings" :key="index">
        {{ warning }}
      </li>
    </ul>
  </template>

  <template v-if="compilerStep === 'scene' && sceneProposals.length">
    <table class="scene-proposal-table">
      <thead>
        <tr>
          <th scope="col"></th>
          <th scope="col">#</th>
          <th scope="col">标题</th>
          <th scope="col">叙述视角</th>
          <th scope="col">目标</th>
          <th scope="col">提醒</th>
          <th scope="col">状态</th>
          <th scope="col"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="proposal in sceneProposals"
          :key="proposal.id"
          :class="{ decided: proposal.status !== 'pending_review' }"
        >
          <td>
            <input
              type="checkbox"
              :checked="selectedSceneProposalIds.includes(proposal.id)"
              :disabled="
                proposal.status !== 'pending_review' || proposal.blocking_errors.length > 0
              "
              :aria-label="`Select scene proposal ${proposal.sequence}`"
              @change="toggleSceneProposalSelection(proposal.id)"
            />
          </td>
          <td>{{ proposal.sequence }}</td>
          <td>
            {{ proposal.title }}
            <SceneProposalChanges :proposal="proposal" />
            <small v-if="proposal.chapter_hint" class="muted">({{ proposal.chapter_hint }})</small>
          </td>
          <td>{{ proposal.pov || '-' }}</td>
          <td class="goal-cell">{{ proposal.goal || '-' }}</td>
          <td>
            <span
              v-if="proposal.blocking_errors.length"
              class="blocking-count"
              :title="proposal.blocking_errors.join('\n')"
            >
              Blocked ({{ proposal.blocking_errors.length }})
            </span>
            <span v-if="proposal.warnings.length" class="warning-count" :title="proposal.warnings.join('\n')">
              {{ proposal.warnings.length }}
            </span>
            <span v-else-if="!proposal.blocking_errors.length">-</span>
          </td>
          <td><span class="step-chip">{{ statusLabel(proposal.status) }}</span></td>
          <td>
            <button
              v-if="proposal.status === 'pending_review'"
              class="secondary"
              type="button"
              @click="rejectSceneProposal(proposal.id)"
            >
              拒绝
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <div class="button-row batch-actions">
      <button
        class="secondary"
        type="button"
        :disabled="
          isCompilingArtifact ||
          !selectedSceneProposalIds.length ||
          !sceneProposals.some(
            (proposal) =>
              proposal.status === 'pending_review' &&
              proposal.blocking_errors.length === 0 &&
              selectedSceneProposalIds.includes(proposal.id)
          )
        "
        @click="acceptSceneProposalBatch(false)"
      >
        Accept Selected ({{ selectedSceneProposalIds.length }})
      </button>
      <button
        class="primary"
        type="button"
        :disabled="
          isCompilingArtifact ||
          !sceneProposals.some(
            (proposal) =>
              proposal.status === 'pending_review' && proposal.blocking_errors.length === 0
          )
        "
        @click="acceptSceneProposalBatch(true)"
      >接受全部待审场景</button>
    </div>
  </template>
  <p
    v-else-if="compilerStep === 'scene'"
    class="save-state"
  >暂无场景建议。先接受第八步的记录，再进行解析。</p>
</section>
</template>

<style scoped>
.compile-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.compile-hint {
  margin: 0;
  color: var(--text-muted, var(--muted));
}

.compile-summary {
  margin: 0;
}

.warning-list {
  margin: 0;
  padding-left: 1.25rem;
  color: var(--warning);
  font-size: 0.85rem;
}

.warning-list li + li {
  margin-top: 0.25rem;
}

.scene-proposal-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.scene-proposal-table th,
.scene-proposal-table td {
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-muted, var(--line));
  padding: 0.4rem 0.5rem;
}

.scene-proposal-table tr.decided {
  opacity: 0.6;
}

.goal-cell {
  max-width: 22rem;
  overflow-wrap: anywhere;
}

.muted {
  color: var(--text-muted, var(--muted));
}

.warning-count {
  background: var(--warning-soft);
  color: var(--warning);
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  font-weight: 600;
  cursor: help;
}

.blocking-count {
  display: inline-block;
  margin-right: 0.25rem;
  padding: 0.05rem 0.5rem;
  border: 1px solid var(--danger);
  color: var(--danger);
  font-weight: 700;
}

.batch-actions {
  justify-content: flex-start;
}
</style>
