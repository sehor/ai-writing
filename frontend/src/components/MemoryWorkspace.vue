<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'

const store = useWorkspaceStore()
const {
  memoryRecords,
  activeMemoryId,
  isSavingMemory,
  isDeletingMemory,
  memoryError,
  memoryDraft,
  memoryStateLabel
} = storeToRefs(store)
const {
  startNewMemoryRecord,
  saveMemoryRecord,
  deleteMemoryRecord,
  statusText
} = store
</script>

<template>
<section class="memory-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Memory / Style</p>
            <h3>Continuity Records</h3>
          </div>
          <button class="primary" type="button" @click="startNewMemoryRecord">
            New Memory Record
          </button>
        </div>

        <div class="memory-grid">
          <aside class="memory-list" aria-label="Memory and style records">
            <button
              v-for="record in memoryRecords"
              :key="record.id"
              :class="{ active: record.id === activeMemoryId }"
              type="button"
              @click="activeMemoryId = record.id"
            >
              <span>{{ record.title }}</span>
              <small>{{ statusText(record.record_type) }}</small>
            </button>
            <p v-if="memoryRecords.length === 0" class="empty-state">
              No Memory / Style records yet.
            </p>
          </aside>

          <form class="memory-editor" @submit.prevent="saveMemoryRecord">
            <div class="memory-fields">
              <label>
                <span>Type</span>
                <select v-model="memoryDraft.record_type">
                  <option value="chapter_summary">Chapter Summary</option>
                  <option value="prose_sample">Prose Sample</option>
                  <option value="voice_sample">Voice Sample</option>
                  <option value="style_rule">Style Rule</option>
                </select>
              </label>
              <label>
                <span>Title</span>
                <input v-model="memoryDraft.title" autocomplete="off" placeholder="Chapter 3 recap" />
              </label>
            </div>

            <div class="memory-fields">
              <label>
                <span>Scope</span>
                <input v-model="memoryDraft.scope" placeholder="chapter_03, Lin voice, city prose" />
              </label>
              <label>
                <span>Source</span>
                <input v-model="memoryDraft.source_ref" placeholder="manuscript/chapter_03" />
              </label>
            </div>

            <label>
              <span>Content</span>
              <textarea
                v-model="memoryDraft.content"
                rows="10"
                placeholder="Summary, sample prose, voice notes, or style rules."
              />
            </label>
            <label>
              <span>Tags</span>
              <input v-model="memoryDraft.tags" placeholder="quiet tension, Lin, archive" />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="memoryError" class="error">{{ memoryError }}</p>
              <p v-else class="save-state">{{ memoryStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeMemoryId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingMemory"
                  @click="deleteMemoryRecord"
                >
                  {{ isDeletingMemory ? 'Deleting...' : 'Delete' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingMemory">
                  {{
                    isSavingMemory
                      ? 'Saving...'
                      : activeMemoryId
                        ? 'Save Record'
                        : 'Create Record'
                  }}
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>
</template>
