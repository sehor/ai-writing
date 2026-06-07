<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../../stores/workspace'

const store = useWorkspaceStore()
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
const { loadWritebackProposals, updateWritebackStatus, statusText, formatJson } = store
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
          <small>{{ statusText(proposal.target) }} / {{ statusText(proposal.status) }}</small>
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
              :disabled="isUpdatingWriteback"
              @click="updateWritebackStatus(activeWritebackProposal.id, 'accepted')"
            >
              Accept
            </button>
          </div>
        </div>

        <dl class="proposal-meta">
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

        <section>
          <p class="eyebrow">Rationale</p>
          <p class="proposal-rationale">
            {{ activeWritebackProposal.rationale || 'No rationale recorded.' }}
          </p>
        </section>
        <section>
          <p class="eyebrow">Structured Payload</p>
          <pre>{{ formatJson(activeWritebackProposal.payload) }}</pre>
        </section>
      </section>
    </div>
  </section>
</template>
