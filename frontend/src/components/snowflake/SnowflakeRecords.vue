<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useSnowflakeStore } from '../../stores/snowflake'
import { useWorkspaceStore } from '../../stores/workspace'

const snowflake = useSnowflakeStore()
const workspace = useWorkspaceStore()
const { records, recordPage, recordTotalPages } = storeToRefs(snowflake)
const recordId = ref('')
const position = ref(1)
const payloadText = ref('{}')
const error = ref('')
const status = ref('')

function openRecord(id: string) {
  const record = records.value.find((item) => item.record_id === id)
  if (!record) return
  recordId.value = record.record_id
  position.value = record.position
  payloadText.value = JSON.stringify(record.payload, null, 2)
  error.value = ''
  status.value = `Revision ${record.revision_no} · ${record.status}`
}

async function saveRecord() {
  error.value = ''
  status.value = ''
  try {
    const payload = JSON.parse(payloadText.value)
    if (!payload || Array.isArray(payload) || typeof payload !== 'object') {
      throw new Error('Record payload must be a JSON object.')
    }
    await snowflake.createRecordRevision(recordId.value.trim(), position.value, payload)
    openRecord(recordId.value.trim())
    status.value = 'Record draft revision saved.'
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Could not save record.'
  }
}

async function decide(id: string, decision: 'accepted' | 'rejected') {
  const revision = records.value.find((item) => item.id === id)
  if (!revision) return
  error.value = ''
  try {
    await snowflake.decideRecordRevision(revision, decision)
    status.value = `Record revision ${decision}.`
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Could not review record.'
  }
}

watch(
  () => [workspace.activeProjectId, workspace.activeStepNumber],
  async () => {
    recordId.value = ''
    payloadText.value = '{}'
    await snowflake.loadRecords()
    if (records.value[0]) openRecord(records.value[0].record_id)
  },
  { immediate: true },
)
</script>

<template>
  <section class="record-workspace">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Structured records</p>
        <h3>Step {{ workspace.activeStepNumber }} record revisions</h3>
      </div>
      <span class="step-chip">page {{ recordPage }} / {{ Math.max(recordTotalPages, 1) }}</span>
    </div>
    <p class="compile-hint">
      Long-form planning is stored as pageable records. Each save creates a draft revision; Accept is the only commit point.
    </p>
    <div class="record-grid">
      <aside class="proposal-list">
        <button v-for="record in records" :key="record.id" type="button" @click="openRecord(record.record_id)">
          <span>{{ record.record_id }}</span>
          <small>r{{ record.revision_no }} · {{ record.status }}</small>
        </button>
        <button type="button" class="secondary" @click="recordId = ''; position = records.length + 1; payloadText = '{}'">
          + New record
        </button>
      </aside>
      <div>
        <label><span>Record ID</span><input v-model="recordId" maxlength="160" /></label>
        <label><span>Position</span><input v-model.number="position" type="number" min="1" max="100000" /></label>
        <label><span>Structured JSON payload</span><textarea v-model="payloadText" rows="14" /></label>
        <p v-if="error" class="error">{{ error }}</p>
        <p v-else class="save-state">{{ status }}</p>
        <div class="button-row">
          <button class="primary" type="button" :disabled="!recordId.trim()" @click="saveRecord">Save record draft</button>
          <template v-if="records.find((item) => item.record_id === recordId && ['draft', 'pending_review'].includes(item.status))">
            <button class="primary" type="button" @click="decide(records.find((item) => item.record_id === recordId)!.id, 'accepted')">Accept</button>
            <button class="secondary danger" type="button" @click="decide(records.find((item) => item.record_id === recordId)!.id, 'rejected')">Reject</button>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.record-workspace { border-top: 1px solid var(--border); padding-top: 1rem; }
.record-grid { display: grid; grid-template-columns: minmax(180px, 0.35fr) minmax(0, 1fr); gap: 1rem; }
@media (max-width: 780px) { .record-grid { grid-template-columns: 1fr; } }
</style>
