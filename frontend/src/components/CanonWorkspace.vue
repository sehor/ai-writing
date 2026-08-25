<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useCanonStore } from '../stores/canon'

const store = useCanonStore()
const {
  canonEntities,
  activeCanonId,
  isSavingCanon,
  isDeletingCanon,
  canonError,
  canonDraft,
  canonStateLabel
} = storeToRefs(store)
const {
  startNewCanonEntity,
  saveCanonEntity,
  deleteCanonEntity
} = store
</script>

<template>
<section class="canon-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Canon DB</p>
            <h3>Confirmed Story Facts</h3>
          </div>
          <button class="primary" type="button" @click="startNewCanonEntity">
            New Canon Entity
          </button>
        </div>

        <div class="canon-grid">
          <aside class="canon-list" aria-label="Canon entities">
            <button
              v-for="entity in canonEntities"
              :key="entity.id"
              :class="{ active: entity.id === activeCanonId }"
              type="button"
              @click="activeCanonId = entity.id"
            >
              <span>{{ entity.name }}</span>
              <small>{{ entity.entity_type }}</small>
            </button>
            <p v-if="canonEntities.length === 0" class="empty-state">
              No Canon entities yet.
            </p>
          </aside>

          <form class="canon-editor" @submit.prevent="saveCanonEntity">
            <div class="canon-fields">
              <label>
                <span>Type</span>
                <select v-model="canonDraft.entity_type">
                  <option value="character">Character</option>
                  <option value="location">Location</option>
                  <option value="item">Item</option>
                  <option value="faction">Faction</option>
                  <option value="rule">Rule</option>
                </select>
              </label>
              <label>
                <span>Name</span>
                <input v-model="canonDraft.name" autocomplete="off" placeholder="Lin Ye" />
              </label>
            </div>

            <label>
              <span>Summary</span>
              <textarea
                v-model="canonDraft.summary"
                rows="3"
                placeholder="What this entity is and why it matters."
              />
            </label>
            <label>
              <span>Current State</span>
              <textarea
                v-model="canonDraft.current_state"
                rows="4"
                placeholder="Confirmed facts at the current point in the story."
              />
            </label>
            <label>
              <span>Constraints</span>
              <textarea
                v-model="canonDraft.constraints"
                rows="4"
                placeholder="Facts future drafts must not violate."
              />
            </label>
            <div class="canon-fields">
              <label>
                <span>Last Seen</span>
                <input v-model="canonDraft.last_seen" placeholder="chapter_12 or scene S032" />
              </label>
            </div>
            <label>
              <span>Timeline Notes</span>
              <textarea
                v-model="canonDraft.timeline_notes"
                rows="5"
                placeholder="Important state changes by chapter or scene."
              />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="canonError" class="error">{{ canonError }}</p>
              <p v-else class="save-state">{{ canonStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeCanonId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingCanon"
                  @click="deleteCanonEntity"
                >
                  {{ isDeletingCanon ? 'Deleting...' : 'Delete' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingCanon">
                  {{ isSavingCanon ? 'Saving...' : activeCanonId ? 'Save Entity' : 'Create Entity' }}
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>
</template>
