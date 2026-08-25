<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { statusText } from '../../utils/format'
import { useManuscriptStore } from '../../stores/manuscript'
import { useReviewsStore } from '../../stores/reviews'

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
} = storeToRefs(store)
const { pendingWritebackCount } = storeToRefs(useReviewsStore())
const { updateProposalStatus } = store
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
              :disabled="isUpdatingProposal"
              @click="updateProposalStatus(activeProposal.id, 'accepted')"
            >
              Accept
            </button>
          </div>
        </div>

        <section>
          <p class="eyebrow">Proposed Draft</p>
          <pre>{{ activeProposal.content }}</pre>
        </section>
        <section>
          <p class="eyebrow">Review Checklist</p>
          <ul>
            <li v-for="item in activeProposal.checklist" :key="item">{{ item }}</li>
          </ul>
        </section>
        <section>
          <p class="eyebrow">Source Context</p>
          <pre>{{ activeProposal.context }}</pre>
        </section>
      </section>
    </div>
  </section>
</template>
