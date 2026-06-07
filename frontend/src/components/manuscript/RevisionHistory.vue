<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../../stores/workspace'

const store = useWorkspaceStore()
const {
  manuscriptRevisions,
  diffLeftRevisionId,
  diffRightRevisionId,
  isLoadingDiff,
  isRestoringRevision,
  isCreatingWriteback,
  isCreatingProviderWriteback,
  isProcessingHermesRevision,
  revisionDiff,
} = storeToRefs(store)
const {
  loadManuscriptRevisions,
  loadRevisionDiff,
  restoreRevision,
  createWritebackFromRevision,
  processRevisionWithHermes,
  revisionLabel,
} = store
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
