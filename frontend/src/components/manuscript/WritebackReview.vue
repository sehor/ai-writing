<script setup lang="ts">
import { computed } from 'vue'
import AnalysisExecution from './AnalysisExecution.vue'
import { useAnalysisJobsStore, analysisJobLabel } from '../../stores/analysisJobs'
import { storeToRefs } from 'pinia'
import { statusText } from '../../utils/format'
import { useCanonStore } from '../../stores/canon'
import { useManuscriptStore } from '../../stores/manuscript'
import { useReviewsStore } from '../../stores/reviews'
import { useNarrativeStore } from '../../stores/narrative'
import { writebackConflict } from '../../domain/writeback'
import type { CanonEntity, ManuscriptRevision, WritebackFieldChange } from '../../types'

const store = useReviewsStore()
const jobsStore = useAnalysisJobsStore()
const {
  writebackProposals,
  hermesProcessReport,
  activeWritebackId,
  isUpdatingWriteback,
  writebackError,
  writebackStatus,
  activeWritebackProposal,
  pendingWritebackCount,
} = storeToRefs(store)
const { canonEntities } = storeToRefs(useCanonStore())
const { threads, error: narrativeError } = storeToRefs(useNarrativeStore())
const isThreadUpdate = computed(() => activeWritebackProposal.value?.target === 'story_thread_status')
const targetThread = computed(() => threads.value.find((thread) => thread.id === activeWritebackProposal.value?.target_record_id))
const clpEvidence = computed(() => {
  const evidence = activeWritebackProposal.value?.payload.evidence
  return Array.isArray(evidence) ? evidence.filter((item): item is { excerpt: string; source_ref: string } =>
    !!item && typeof item === 'object' && typeof item.excerpt === 'string') : []
})
const { manuscriptRevisions } = storeToRefs(useManuscriptStore())
const { loadWritebackProposals, updateWritebackStatus } = store

const FIELD_LABELS: Record<string, string> = {
  entity_type: '设定类型',
  name: '名称',
  summary: '摘要',
  current_state: '当前状态',
  constraints: '约束条件',
  last_seen: '最后出现位置',
  timeline_notes: '时间线备注',
}

function fieldLabel(field: string) {
  return FIELD_LABELS[field] ?? field
}

const isUpdateProposal = computed(
  () => activeWritebackProposal.value?.action === 'update'
)

const changeEntries = computed<[string, WritebackFieldChange][]>(() =>
  Object.entries(
    activeWritebackProposal.value?.changes ?? {}
  ) as [string, WritebackFieldChange][]
)

const targetRecord = computed<CanonEntity | undefined>(() => {
  const proposal = activeWritebackProposal.value
  if (!proposal?.target_record_id) {
    return undefined
  }
  return canonEntities.value.find((entity) => entity.id === proposal.target_record_id)
})

const conflictReason = computed(() => {
  const proposal = activeWritebackProposal.value
  return proposal ? writebackConflict(proposal, canonEntities.value, threads.value) : ''
})
const versionConflict = computed(() => !!conflictReason.value)

const evidenceRevision = computed<ManuscriptRevision | undefined>(() => {
  const sourceRef = activeWritebackProposal.value?.source_ref ?? ''
  const match = /^manuscript_revision:(.+)$/.exec(sourceRef)
  if (!match) {
    return undefined
  }
  return manuscriptRevisions.value.find((revision) => revision.id === match[1])
})

const evidenceExcerpt = computed(() => {
  const revision = evidenceRevision.value
  if (!revision) {
    return ''
  }
  const content = revision.content
  const afterValues = changeEntries.value.map(([, change]) => change.after).filter(Boolean)
  const hit = afterValues.length
    ? content.indexOf(afterValues[0])
    : -1
  if (hit >= 0) {
    const start = Math.max(0, hit - 200)
    const end = Math.min(content.length, hit + afterValues[0].length + 400)
    return (start > 0 ? '...' : '') + content.slice(start, end) + (end < content.length ? '...' : '')
  }
  return content.length > 600 ? `${content.slice(0, 600)}...` : content
})

function formatJson(value: Record<string, unknown> | undefined) {
  return JSON.stringify(value ?? {}, null, 2)
}
</script>

<template>
  <section class="writeback-review">
    <div class="panel-header">
      <div>
        <h3>设定、记忆与叙事变更</h3>
      </div>
      <div class="button-row">
        <span class="step-chip">{{ pendingWritebackCount }} 待审</span>
        <button class="secondary" type="button" @click="loadWritebackProposals()">刷新</button>
      </div>
    </div>

    <p class="status-text">候选不是已确认事实。保存后的本地规则不能证明完整语义无矛盾；Provider 仅手动调用，CLP 仅在显式配置后运行。</p>
    <details>
      <summary>检查范围与执行记录</summary>
      <button type="button" class="secondary" @click="store.loadPostAcceptAnalysisJobs()">刷新执行记录</button>
      <p v-if="jobsStore.error" role="alert">{{ jobsStore.error }}</p>
      <p v-if="!jobsStore.jobs.length">暂无执行记录；不能据此认为检查已完成。</p>
      <article v-for="job in jobsStore.jobs.slice(0, 8)" :key="job.id">
        <h4>{{ analysisJobLabel(job.job_type) }}</h4><AnalysisExecution :job="job" />
      </article>
      <p>更多任务及失败重试见“版本历史”。外部模型效果尚未人工验收；运行时修复或降级不代表效果认证。</p>
    </details>
    <p v-if="writebackError" class="error">{{ writebackError }}</p>
    <p v-else-if="writebackStatus" class="save-state">{{ writebackStatus }}</p>

    <section v-if="hermesProcessReport" class="export-output">
      <div class="panel-header compact">
        <div>
          <p class="eyebrow">Hermes {{ hermesProcessReport.status }}</p>
          <h4>{{ hermesProcessReport.processed_source_ref }}</h4>
        </div>
        <span class="step-chip">{{ hermesProcessReport.wiki_changes.length }} wiki changes</span>
      </div>
      <p class="proposal-rationale">{{ hermesProcessReport.summary }}</p>
      <dl v-if="hermesProcessReport.wiki_changes.length" class="proposal-meta">
        <div
          v-for="change in hermesProcessReport.wiki_changes"
          :key="`${change.action}-${change.path}`"
        >
          <dt>{{ change.action }}</dt>
          <dd>{{ change.path }} - {{ change.reason }}</dd>
        </div>
      </dl>
      <dl v-if="hermesProcessReport.issues.length" class="proposal-meta">
        <div
          v-for="issue in hermesProcessReport.issues"
          :key="`${issue.code}-${issue.message}`"
        >
          <dt>{{ issue.severity }} / {{ issue.code }}</dt>
          <dd>{{ issue.message }}</dd>
        </div>
      </dl>
    </section>

    <div class="proposal-grid">
      <aside class="proposal-list" aria-label="Write-back proposals">
        <button
          v-for="proposal in writebackProposals"
          :key="proposal.id"
          :class="{ active: proposal.id === activeWritebackId }"
          type="button"
          @click="activeWritebackId = proposal.id"
        >
          <span>{{ proposal.title }}</span>
          <small>{{ statusText(proposal.action) }} / {{ statusText(proposal.status) }}</small>
        </button>
        <p v-if="writebackProposals.length === 0" class="empty-state">
          没有待审核的回写建议。
        </p>
      </aside>

      <section v-if="activeWritebackProposal" class="proposal-detail">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">{{ statusText(activeWritebackProposal.status) }}</p>
            <h4>{{ activeWritebackProposal.title }}</h4>
          </div>
          <div class="button-row">
            <button
              v-if="activeWritebackProposal.status === 'pending_review'"
              class="secondary danger"
              type="button"
              :disabled="isUpdatingWriteback"
              @click="updateWritebackStatus(activeWritebackProposal.id, 'rejected')"
            >
              拒绝
            </button>
            <button
              v-if="activeWritebackProposal.status === 'pending_review'"
              class="primary"
              type="button"
              :disabled="isUpdatingWriteback || versionConflict"
              :title="
                versionConflict
                  ? '建议创建后，目标记录已更新。请核对当前内容。'
                  : ''
              "
              @click="updateWritebackStatus(activeWritebackProposal.id, 'accepted')"
            >
              接受
            </button>
          </div>
        </div>

        <p v-if="versionConflict && activeWritebackProposal.status === 'pending_review'" class="error" role="alert">
          Conflict warning: {{ conflictReason }}
        </p>
        <p v-if="narrativeError && isThreadUpdate" class="error">{{ narrativeError }}</p>

        <dl class="proposal-meta">
          <div>
            <dt>操作</dt>
            <dd>{{ statusText(activeWritebackProposal.action) }}</dd>
          </div>
          <div>
            <dt>目标</dt>
            <dd>{{ statusText(activeWritebackProposal.target) }}</dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>{{ activeWritebackProposal.source_ref || 'none' }}</dd>
          </div>
          <div>
            <dt>已应用记录</dt>
            <dd>{{ activeWritebackProposal.applied_record_id || 'not applied' }}</dd>
          </div>
        </dl>

        <section v-if="isUpdateProposal && !isThreadUpdate">
          <p class="eyebrow">目标记录</p>
          <dl class="proposal-meta">
            <div>
              <dt>记录</dt>
              <dd>
                <template v-if="targetRecord">
                  {{ targetRecord.entity_type }} / {{ targetRecord.name }}
                </template>
                <template v-else>
                  {{ activeWritebackProposal.target_record_id || 'unresolved' }} (missing)
                </template>
              </dd>
            </div>
            <div>
              <dt>当前版本</dt>
              <dd>{{ targetRecord ? `v${targetRecord.version}` : 'unknown' }}</dd>
            </div>
            <div>
              <dt>预期版本</dt>
              <dd>
                {{
                  activeWritebackProposal.expected_version
                    ? `v${activeWritebackProposal.expected_version}`
                    : 'not set'
                }}
              </dd>
            </div>
          </dl>
        </section>

        <section v-if="isThreadUpdate" class="thread-status-proposal" data-testid="thread-status-proposal">
          <h4>{{ targetThread?.title || activeWritebackProposal.target_record_id }}</h4>
          <p>当前：{{ targetThread?.status ?? '未加载' }} · 提案基于：{{ activeWritebackProposal.payload.from_state }}</p>
          <p>建议：{{ activeWritebackProposal.payload.proposed_state }} · 置信度：{{ activeWritebackProposal.payload.confidence }}</p>
        </section>
        <section v-if="activeWritebackProposal.target === 'narrative_relation'" class="relation-proposal">
          <p class="eyebrow">叙事关系</p>
          <p>{{ activeWritebackProposal.payload.source }} → {{ activeWritebackProposal.payload.relation }} → {{ activeWritebackProposal.payload.target }}</p>
          <p>场景区间 {{ activeWritebackProposal.payload.valid_from }}–{{ activeWritebackProposal.payload.valid_to ?? '持续' }} · 置信度 {{ activeWritebackProposal.payload.confidence }}</p>
        </section>
        <section
          v-if="['story_thread', 'story_thread_event'].includes(activeWritebackProposal.target)"
          class="thread-status-proposal"
        >
          <p class="eyebrow">故事线建议</p>
          <p>
            {{ activeWritebackProposal.target === 'story_thread'
              ? '接受后才会创建故事线。'
              : '场景与故事线均存在后，才会添加关联事件。' }}
          </p>
        </section>
        <section v-if="clpEvidence.length" class="clp-evidence">
          <p class="eyebrow">提取依据</p>
          <blockquote v-for="(item, index) in clpEvidence" :key="index">{{ item.excerpt }} <small>{{ item.source_ref }}</small></blockquote>
        </section>
        <section>
          <p class="eyebrow">依据说明</p>
          <p class="proposal-rationale">
            {{ activeWritebackProposal.rationale || '暂无依据说明。' }}
          </p>
        </section>

        <section v-if="isUpdateProposal && changeEntries.length">
          <p class="eyebrow">建议变更</p>
          <table class="writeback-changes">
            <thead>
              <tr>
                <th scope="col">字段</th>
                <th scope="col">当前内容</th>
                <th scope="col">建议内容</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="[field, change] in changeEntries" :key="field">
                <th scope="row">{{ fieldLabel(field) }}</th>
                <td>{{ targetRecord ? String(targetRecord[field as keyof CanonEntity] ?? change.before) : change.before }}</td>
                <td>{{ change.after }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section v-if="evidenceExcerpt">
          <p class="eyebrow">依据<template v-if="evidenceRevision">
              - {{ evidenceRevision.title }} v{{ evidenceRevision.version }}
            </template>
          </p>
          <pre class="evidence-excerpt">{{ evidenceExcerpt }}</pre>
        </section>

        <section v-if="!isUpdateProposal">
          <p class="eyebrow">结构化数据</p>
          <pre>{{ formatJson(activeWritebackProposal.payload) }}</pre>
        </section>
      </section>
    </div>
  </section>
</template>
