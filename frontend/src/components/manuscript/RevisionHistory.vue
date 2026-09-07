<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useManuscriptStore } from '../../stores/manuscript'
import { useReviewsStore } from '../../stores/reviews'
import { useAnalysisJobsStore, analysisJobState } from '../../stores/analysisJobs'
import AnalysisExecution from './AnalysisExecution.vue'
import type { FindingSeverity, OutboxJobStatus } from '../../types'

const store = useManuscriptStore()
const reviews = useReviewsStore()
const jobsStore = useAnalysisJobsStore()
const { error: jobsError, retryingId, canLoadMore } = storeToRefs(jobsStore)
const {
  manuscriptRevisions,
  diffLeftRevisionId,
  diffRightRevisionId,
  isLoadingDiff,
  isRestoringRevision,
  revisionDiff,
} = storeToRefs(store)
const {
  isCreatingWriteback,
  isCreatingProviderWriteback,
  isProcessingHermesRevision,
  isRunningConsistencyCheck,
  consistencyReport,
  consistencyRevisionId,
  consistencyError,
  consistencyStatus,
  postAcceptJobs,
} = storeToRefs(reviews)
const {
  loadManuscriptRevisions,
  loadRevisionDiff,
  restoreRevision,
  revisionLabel,
} = store
const {
  createWritebackFromRevision,
  processRevisionWithHermes,
  runConsistencyCheck,
  loadPostAcceptAnalysisJobs,
  retryPostAcceptAnalysisJob,
  analysisJobLabel,
} = reviews

const checkedRevisionLabel = computed(() => {
  if (!consistencyRevisionId.value) return ''
  const revision = manuscriptRevisions.value.find(
    (item) => item.id === consistencyRevisionId.value,
  )
  return revision ? revisionLabel(revision) : consistencyRevisionId.value
})

const severityClass = (severity: FindingSeverity) => `severity-${severity}`

const jobStatusClass = (status: OutboxJobStatus) => `job-status-${status}`

const pendingAnalysisCount = computed(
  () => postAcceptJobs.value.filter((job) => job.status === 'pending' || job.status === 'processing').length
)
</script>

<template>
  <section class="revision-history">
    <div class="panel-header">
      <div>
        <h3>已保存版本</h3>
      </div>
      <button class="secondary" type="button" @click="loadManuscriptRevisions()">刷新</button>
    </div>

    <div v-if="manuscriptRevisions.length" class="revision-tools">
      <label>
        <span>基准版本</span>
        <select v-model="diffLeftRevisionId">
          <option
            v-for="revision in manuscriptRevisions"
            :key="`left-${revision.id}`"
            :value="revision.id"
          >
            {{ revisionLabel(revision) }}
          </option>
        </select>
      </label>
      <label>
        <span>对比版本</span>
        <select v-model="diffRightRevisionId">
          <option
            v-for="revision in manuscriptRevisions"
            :key="`right-${revision.id}`"
            :value="revision.id"
          >
            {{ revisionLabel(revision) }}
          </option>
        </select>
      </label>
      <button
        class="secondary"
        type="button"
        :disabled="isLoadingDiff"
        @click="loadRevisionDiff"
      >
        {{ isLoadingDiff ? '加载中…' : '比较版本' }}
      </button>
    </div>

    <section v-if="revisionDiff" class="diff-output">
      <div class="panel-header compact">
        <div>
          <h4>{{ revisionDiff.left_title }} -> {{ revisionDiff.right_title }}</h4>
        </div>
        <span class="step-chip">{{ revisionDiff.diff_lines.length }} lines</span>
      </div>
      <pre>{{ revisionDiff.diff_lines.join('\n') }}</pre>
    </section>

    <!-- P1-07: automatic analyses scheduled when a proposal was accepted -->
    <section class="post-accept-analysis">
      <div class="panel-header compact">
        <div>
          <h4>接受后自动安排分析</h4>
        </div>
        <div class="button-row">
          <span v-if="pendingAnalysisCount" class="step-chip">
            {{ pendingAnalysisCount }} running
          </span>
          <button class="secondary" type="button" @click="loadPostAcceptAnalysisJobs()">
            刷新
          </button>
        </div>
      </div>

      <p v-if="jobsError" class="error-text" role="alert">{{ jobsError }}</p>
      <p v-if="!postAcceptJobs.length" class="empty-state">暂无正文分析任务。保存正文后会自动显示，也可以刷新重新加载。</p>
      <article v-for="job in postAcceptJobs" :key="job.id" class="analysis-job-item" :data-aggregate-id="job.aggregate_id">
        <div class="panel-header compact">
          <div>
            <span :class="['severity-chip', jobStatusClass(job.status)]">{{ analysisJobState(job) }}</span>
            <strong>{{ analysisJobLabel(job.job_type) }}</strong>
          </div>
          <small>{{ job.completed_at || job.created_at }}</small>
        </div>
        <small>{{ job.aggregate_id }} · attempt {{ job.attempt_count }}</small>
        <AnalysisExecution :job="job" />
        <p v-if="job.last_error" class="error-text">{{ job.last_error }}</p>
        <div v-if="job.status === 'failed'" class="button-row">
          <button class="secondary" type="button" :disabled="!!retryingId" @click="retryPostAcceptAnalysisJob(job.id)">
            {{ retryingId === job.id ? 'Retrying...' : '重试' }}
          </button>
        </div>
      </article>
      <button v-if="canLoadMore" type="button" class="secondary" @click="jobsStore.loadMore()">加载更多历史任务</button>
      <p class="status-text">保存仅自动运行本地规则和已显式配置的 CLP；不会自动调用 Provider。零问题不等于完整语义无矛盾。回写候选须人工审核。</p>
    </section>

    <section v-if="consistencyReport || consistencyError" class="consistency-report">
      <div class="panel-header compact">
        <div>
          <h4 v-if="checkedRevisionLabel">{{ checkedRevisionLabel }}</h4>
        </div>
        <span v-if="consistencyReport" class="step-chip">
          run v{{ consistencyReport.run_version }}{{ consistencyReport.cached ? ' · cached' : '' }}
        </span>
      </div>

      <p v-if="consistencyError" class="error-text">{{ consistencyError }}</p>
      <p v-if="consistencyStatus" class="status-text">{{ consistencyStatus }}</p>

      <div v-if="consistencyReport" class="finding-summary">
        <span :class="['severity-chip', severityClass('critical')]">
          {{ consistencyReport.summary.critical_count }} 严重
        </span>
        <span :class="['severity-chip', severityClass('warning')]">
          {{ consistencyReport.summary.warning_count }} warnings
        </span>
        <span :class="['severity-chip', severityClass('info')]">
          {{ consistencyReport.summary.info_count }} info
        </span>
      </div>

      <article
        v-for="finding in consistencyReport?.findings ?? []"
        :key="finding.id"
        class="finding-item"
      >
        <div class="panel-header compact">
          <div>
            <span :class="['severity-chip', severityClass(finding.severity)]">
              {{ finding.severity }}
            </span>
            <strong>{{ finding.title }}</strong>
          </div>
          <small>{{ finding.rule_code }} · {{ finding.confidence }}</small>
        </div>
        <p>{{ finding.description }}</p>
        <blockquote class="finding-evidence">{{ finding.manuscript_excerpt }}</blockquote>
        <dl class="finding-details">
          <div>
            <dt>预期</dt>
            <dd>{{ finding.expected_value }}</dd>
          </div>
          <div>
            <dt>实际</dt>
            <dd>{{ finding.observed_value }}</dd>
          </div>
          <div v-if="finding.canon_field">
            <dt>故事设定</dt>
            <dd>{{ finding.canon_entity_id ?? 'scene contract' }} · {{ finding.canon_field }}</dd>
          </div>
        </dl>
        <p class="finding-action"><span>建议：</span> {{ finding.suggested_action }}</p>
      </article>
    </section>

    <div class="revision-list">
      <article v-for="revision in manuscriptRevisions" :key="revision.id" class="revision-item">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">Version {{ revision.version }}</p>
            <h4>{{ revision.title }}</h4>
          </div>
          <div class="revision-actions">
            <small>{{ revision.created_at }}</small>
            <div class="button-row">
              <button
                class="secondary"
                type="button"
                :disabled="isRunningConsistencyCheck"
                @click="runConsistencyCheck(revision.id)"
              >一致性检查</button>
              <button
                class="secondary"
                type="button"
                :disabled="isProcessingHermesRevision"
                @click="processRevisionWithHermes(revision.id)"
              >
                {{ isProcessingHermesRevision ? 'Processing...' : '提取正文信息' }}
              </button>
              <button
                class="secondary"
                type="button"
                :disabled="isCreatingWriteback"
                @click="createWritebackFromRevision(revision.id)"
              >生成本地建议</button>
              <button
                class="secondary"
                type="button"
                :disabled="isCreatingProviderWriteback"
                @click="createWritebackFromRevision(revision.id, true)"
              >使用模型生成建议</button>
              <button
                class="secondary danger"
                type="button"
                :disabled="isRestoringRevision"
                @click="restoreRevision(revision.id)"
              >
                恢复版本
              </button>
            </div>
          </div>
        </div>
        <pre>{{ revision.content }}</pre>
      </article>
      <p v-if="manuscriptRevisions.length === 0" class="empty-state">保存正文后，版本会出现在这里。</p>
    </div>
  </section>
</template>
