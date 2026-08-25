<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useManuscriptStore } from '../../stores/manuscript'
import { useReviewsStore } from '../../stores/reviews'
import type { FindingSeverity, OutboxJobStatus } from '../../types'

const store = useManuscriptStore()
const reviews = useReviewsStore()
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
        <p class="eyebrow">Version History</p>
        <h3>Accepted Revisions</h3>
      </div>
      <button class="secondary" type="button" @click="loadManuscriptRevisions()">Refresh</button>
    </div>

    <div v-if="manuscriptRevisions.length" class="revision-tools">
      <label>
        <span>Base Revision</span>
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
        <span>Compare Revision</span>
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
        {{ isLoadingDiff ? 'Loading...' : 'Compare' }}
      </button>
    </div>

    <section v-if="revisionDiff" class="diff-output">
      <div class="panel-header compact">
        <div>
          <p class="eyebrow">Revision Diff</p>
          <h4>{{ revisionDiff.left_title }} -> {{ revisionDiff.right_title }}</h4>
        </div>
        <span class="step-chip">{{ revisionDiff.diff_lines.length }} lines</span>
      </div>
      <pre>{{ revisionDiff.diff_lines.join('\n') }}</pre>
    </section>

    <!-- P1-07: automatic analyses scheduled when a proposal was accepted -->
    <section v-if="postAcceptJobs.length" class="post-accept-analysis">
      <div class="panel-header compact">
        <div>
          <p class="eyebrow">Post-Acceptance Analysis</p>
          <h4>Scheduled automatically on acceptance</h4>
        </div>
        <div class="button-row">
          <span v-if="pendingAnalysisCount" class="step-chip">
            {{ pendingAnalysisCount }} running
          </span>
          <button class="secondary" type="button" @click="loadPostAcceptAnalysisJobs()">
            Refresh
          </button>
        </div>
      </div>

      <article v-for="job in postAcceptJobs" :key="job.id" class="analysis-job-item">
        <div class="panel-header compact">
          <div>
            <span :class="['severity-chip', jobStatusClass(job.status)]">{{ job.status }}</span>
            <strong>{{ analysisJobLabel(job.job_type) }}</strong>
          </div>
          <small>{{ job.completed_at || job.created_at }}</small>
        </div>
        <p v-if="job.last_error" class="error-text">{{ job.last_error }}</p>
        <div v-if="job.status === 'failed'" class="button-row">
          <button class="secondary" type="button" @click="retryPostAcceptAnalysisJob(job.id)">
            Retry
          </button>
        </div>
      </article>
      <p class="status-text">
        Analysis runs automatically; its write-back suggestions stay pending for review.
      </p>
    </section>

    <section v-if="consistencyReport || consistencyError" class="consistency-report">
      <div class="panel-header compact">
        <div>
          <p class="eyebrow">Consistency Report</p>
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
          {{ consistencyReport.summary.critical_count }} critical
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
            <dt>Expected</dt>
            <dd>{{ finding.expected_value }}</dd>
          </div>
          <div>
            <dt>Observed</dt>
            <dd>{{ finding.observed_value }}</dd>
          </div>
          <div v-if="finding.canon_field">
            <dt>Canon</dt>
            <dd>{{ finding.canon_entity_id ?? 'scene contract' }} · {{ finding.canon_field }}</dd>
          </div>
        </dl>
        <p class="finding-action"><span>Suggested:</span> {{ finding.suggested_action }}</p>
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
              >
                Consistency
              </button>
              <button
                class="secondary"
                type="button"
                :disabled="isProcessingHermesRevision"
                @click="processRevisionWithHermes(revision.id)"
              >
                {{ isProcessingHermesRevision ? 'Processing...' : 'Process with Hermes' }}
              </button>
              <button
                class="secondary"
                type="button"
                :disabled="isCreatingWriteback"
                @click="createWritebackFromRevision(revision.id)"
              >
                Local Suggest
              </button>
              <button
                class="secondary"
                type="button"
                :disabled="isCreatingProviderWriteback"
                @click="createWritebackFromRevision(revision.id, true)"
              >
                Provider Suggest
              </button>
              <button
                class="secondary danger"
                type="button"
                :disabled="isRestoringRevision"
                @click="restoreRevision(revision.id)"
              >
                Restore
              </button>
            </div>
          </div>
        </div>
        <pre>{{ revision.content }}</pre>
      </article>
      <p v-if="manuscriptRevisions.length === 0" class="empty-state">
        No accepted revisions yet.
      </p>
    </div>
  </section>
</template>
