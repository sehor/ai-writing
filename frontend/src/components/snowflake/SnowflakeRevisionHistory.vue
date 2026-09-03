<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useSnowflakeStore } from '../../stores/snowflake'

const snowflake = useSnowflakeStore()
const { revisions, activeRevisionId } = storeToRefs(snowflake)
</script>

<template>
  <aside class="revision-history" aria-labelledby="revision-history-title">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Audit trail</p>
        <h3 id="revision-history-title">Revision history</h3>
      </div>
      <span class="step-chip">{{ revisions.length }}</span>
    </div>
    <ol v-if="revisions.length" class="revision-list">
      <li v-for="revision in revisions" :key="revision.id">
        <button
          type="button"
          class="revision-button"
          :class="{ active: revision.id === activeRevisionId }"
          :aria-current="revision.id === activeRevisionId ? 'true' : undefined"
          @click="snowflake.openRevision(revision.id)"
        >
          <span>
            <strong>Revision {{ revision.revision_no }}</strong>
            <small>{{ revision.source }} · {{ revision.created_at }}</small>
          </span>
          <span class="step-chip">{{ revision.status.replace('_', ' ') }}</span>
        </button>
      </li>
    </ol>
    <p v-else class="save-state">No revisions for this step yet.</p>
  </aside>
</template>

<style scoped>
.revision-history {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.revision-list {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.revision-button {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--border-muted, #d6d3d1);
  background: transparent;
  color: inherit;
  text-align: left;
}

.revision-button.active {
  border-color: var(--accent, #9a3412);
  background: var(--surface-muted, #fafaf9);
}

.revision-button span:first-child {
  display: grid;
  gap: 0.25rem;
}

.revision-button small {
  color: var(--text-muted, #6b7280);
}
</style>
