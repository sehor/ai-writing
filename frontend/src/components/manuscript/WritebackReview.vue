<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { statusText } from '../../utils/format'
import { useCanonStore } from '../../stores/canon'
import { useManuscriptStore } from '../../stores/manuscript'
import { useReviewsStore } from '../../stores/reviews'
import type { CanonEntity, ManuscriptRevision, WritebackFieldChange } from '../../types'

const store = useReviewsStore()
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
const { manuscriptRevisions } = storeToRefs(useManuscriptStore())
const { loadWritebackProposals, updateWritebackStatus } = store

const FIELD_LABELS: Record<string, string> = {
  entity_type: 'Entity type',
  name: 'Name',
  summary: 'Summary',
  current_state: 'Current state',
  constraints: 'Constraints',
  last_seen: 'Last seen',
  timeline_notes: 'Timeline notes',
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

const versionConflict = computed(() => {
  const proposal = activeWritebackProposal.value
  if (!proposal || proposal.action !== 'update') {
    return false
  }
  if (!targetRecord.value) {
    return true
  }
  return targetRecord.value.version !== proposal.expected_version
})

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
        <p class="eyebrow">State Write-back</p>
        <h3>Canon / Memory Proposals</h3>
      </div>
      <div class="button-row">
        <span class="step-chip">{{ pendingWritebackCount }} pending</span>
        <button class="secondary" type="button" @click="loadWritebackProposals()">Refresh</button>
      </div>
    </div>

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
          No write-back proposals yet.
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
              Reject
            </button>
            <button
              v-if="activeWritebackProposal.status === 'pending_review'"
              class="primary"
              type="button"
              :disabled="isUpdatingWriteback || versionConflict"
              :title="
                versionConflict
                  ? 'The target record changed since this proposal was created.'
                  : ''
              "
              @click="updateWritebackStatus(activeWritebackProposal.id, 'accepted')"
            >
              Accept
            </button>
          </div>
        </div>

        <p v-if="isUpdateProposal && versionConflict && activeWritebackProposal.status === 'pending_review'" class="error">
          Conflict warning: the target record changed since this proposal was created.
          Review the current values below and regenerate the proposal if needed.
        </p>

        <dl class="proposal-meta">
          <div>
            <dt>Action</dt>
            <dd>{{ statusText(activeWritebackProposal.action) }}</dd>
          </div>
          <div>
            <dt>Target</dt>
            <dd>{{ statusText(activeWritebackProposal.target) }}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{{ activeWritebackProposal.source_ref || 'none' }}</dd>
          </div>
          <div>
            <dt>Applied Record</dt>
            <dd>{{ activeWritebackProposal.applied_record_id || 'not applied' }}</dd>
          </div>
        </dl>

        <section v-if="isUpdateProposal">
          <p class="eyebrow">Target Record</p>
          <dl class="proposal-meta">
            <div>
              <dt>Record</dt>
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
              <dt>Current version</dt>
              <dd>{{ targetRecord ? `v${targetRecord.version}` : 'unknown' }}</dd>
            </div>
            <div>
              <dt>Expected version</dt>
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

        <section>
          <p class="eyebrow">Rationale</p>
          <p class="proposal-rationale">
            {{ activeWritebackProposal.rationale || 'No rationale recorded.' }}
          </p>
        </section>

        <section v-if="isUpdateProposal && changeEntries.length">
          <p class="eyebrow">Proposed Changes</p>
          <table class="writeback-changes">
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Current value</th>
                <th scope="col">Proposed value</th>
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
          <p class="eyebrow">
            Evidence
            <template v-if="evidenceRevision">
              - {{ evidenceRevision.title }} v{{ evidenceRevision.version }}
            </template>
          </p>
          <pre class="evidence-excerpt">{{ evidenceExcerpt }}</pre>
        </section>

        <section v-if="!isUpdateProposal">
          <p class="eyebrow">Structured Payload</p>
          <pre>{{ formatJson(activeWritebackProposal.payload) }}</pre>
        </section>
      </section>
    </div>
  </section>
</template>
