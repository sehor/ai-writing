<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { statusText } from '../../utils/format'
import { useReviewsStore } from '../../stores/reviews'

const store = useReviewsStore()
const {
  referenceSuggestions,
  activeReferenceId,
  isGeneratingReference,
  isGeneratingProviderReference,
  isUpdatingReference,
  referenceError,
  referenceStatus,
  referenceDraft,
  activeReferenceSuggestion,
  pendingReferenceCount,
} = storeToRefs(store)
const {
  loadReferenceSuggestions,
  generateReferenceSuggestion,
  updateReferenceStatus,
  referenceWarnings
} = store
</script>

<template>
  <section class="reference-workspace">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Structured Copilot</p>
        <h3>Reference Suggestions</h3>
      </div>
      <div class="button-row">
        <span class="step-chip">{{ pendingReferenceCount }} pending</span>
        <button class="secondary" type="button" @click="loadReferenceSuggestions()">Refresh</button>
      </div>
    </div>

    <form class="reference-form" @submit.prevent="generateReferenceSuggestion(false)">
      <div class="scene-fields">
        <label>
          <span>Request</span>
          <select v-model="referenceDraft.suggestion_type">
            <option value="brainstorm">Brainstorm</option>
            <option value="scene_bridge">Scene bridge</option>
            <option value="conflict_options">Conflict options</option>
            <option value="character_motivation">Character motivation</option>
            <option value="canon_gap">Canon gap</option>
            <option value="prose_reference">Prose reference</option>
            <option value="structure_fix">Structure fix</option>
          </select>
        </label>
        <label>
          <span>Scope</span>
          <select v-model="referenceDraft.scope_type">
            <option value="project">Project</option>
            <option value="snowflake_step">Snowflake step</option>
            <option value="scene">Scene</option>
            <option value="canon_entity">Canon entity</option>
            <option value="memory_record">Memory record</option>
            <option value="manuscript_scene">Manuscript scene</option>
            <option value="graph">Graph</option>
          </select>
        </label>
        <label>
          <span>Scope Ref</span>
          <input
            v-model="referenceDraft.scope_ref"
            autocomplete="off"
            placeholder="Scene id, step number, or leave blank"
          />
        </label>
      </div>

      <label>
        <span>Writing Problem</span>
        <textarea
          v-model="referenceDraft.author_problem"
          rows="3"
          placeholder="What is blocked, unclear, or structurally weak?"
        />
      </label>
      <label>
        <span>Desired Output</span>
        <input
          v-model="referenceDraft.desired_output"
          autocomplete="off"
          placeholder="Three options, one bridge, motivation notes..."
        />
      </label>

      <div class="form-actions artifact-actions">
        <p v-if="referenceError" class="error">{{ referenceError }}</p>
        <p v-else-if="referenceStatus" class="save-state">{{ referenceStatus }}</p>
        <p v-else class="save-state">Reference suggestions are advisory and reviewable.</p>
        <div class="button-row">
          <button
            class="secondary"
            type="button"
            :disabled="isGeneratingProviderReference"
            @click="generateReferenceSuggestion(true)"
          >
            {{ isGeneratingProviderReference ? 'Generating...' : 'Provider Reference' }}
          </button>
          <button class="primary" type="submit" :disabled="isGeneratingReference">
            {{ isGeneratingReference ? 'Generating...' : 'Generate Reference' }}
          </button>
        </div>
      </div>
    </form>

    <div class="proposal-grid">
      <aside class="proposal-list" aria-label="Reference suggestions">
        <button
          v-for="suggestion in referenceSuggestions"
          :key="suggestion.id"
          :class="{ active: suggestion.id === activeReferenceId }"
          type="button"
          @click="activeReferenceId = suggestion.id"
        >
          <span>{{ suggestion.title }}</span>
          <small>{{ statusText(suggestion.suggestion_type) }} / {{ statusText(suggestion.status) }}</small>
        </button>
        <p v-if="referenceSuggestions.length === 0" class="empty-state">
          No reference suggestions yet.
        </p>
      </aside>

      <section v-if="activeReferenceSuggestion" class="proposal-detail">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">{{ statusText(activeReferenceSuggestion.status) }}</p>
            <h4>{{ activeReferenceSuggestion.title }}</h4>
          </div>
          <div class="button-row">
            <button
              v-if="activeReferenceSuggestion.status === 'pending_review'"
              class="secondary danger"
              type="button"
              :disabled="isUpdatingReference"
              @click="updateReferenceStatus(activeReferenceSuggestion.id, 'rejected')"
            >
              Reject
            </button>
            <button
              v-if="activeReferenceSuggestion.status === 'pending_review'"
              class="primary"
              type="button"
              :disabled="isUpdatingReference"
              @click="updateReferenceStatus(activeReferenceSuggestion.id, 'accepted')"
            >
              Accept Reference
            </button>
          </div>
        </div>

        <section>
          <p class="eyebrow">Suggestion</p>
          <pre>{{ activeReferenceSuggestion.content }}</pre>
        </section>
        <section>
          <p class="eyebrow">Rationale</p>
          <p class="proposal-rationale">{{ activeReferenceSuggestion.rationale }}</p>
        </section>
        <section v-if="referenceWarnings(activeReferenceSuggestion).length">
          <p class="eyebrow">Warnings and Notes</p>
          <ul>
            <li v-for="item in referenceWarnings(activeReferenceSuggestion)" :key="item">
              {{ item }}
            </li>
          </ul>
        </section>
        <details>
          <summary>Used Context · 展开查看</summary>
          <pre>{{ activeReferenceSuggestion.used_context }}</pre>
        </details>
      </section>
    </div>
  </section>
</template>
