<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../../stores/workspace'

const store = useWorkspaceStore()
const {
  manuscriptScenes,
  editingManuscriptSceneId,
  isSavingManuscriptScene,
  isExportingManuscript,
  manuscriptEditTitle,
  manuscriptEditContent,
  manuscriptExport,
} = storeToRefs(store)
const {
  loadManuscriptScenes,
  exportManuscript,
  startEditingManuscriptScene,
  cancelEditingManuscriptScene,
  saveManuscriptSceneEdit,
  chapterTitleForScene,
} = store
</script>

<template>
  <section class="accepted-manuscript">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Accepted Manuscript</p>
        <h3>Current Scene Drafts</h3>
      </div>
      <div class="button-row">
        <button
          class="secondary"
          type="button"
          :disabled="isExportingManuscript"
          @click="exportManuscript"
        >
          {{ isExportingManuscript ? 'Exporting...' : 'Export Markdown' }}
        </button>
        <button class="secondary" type="button" @click="loadManuscriptScenes()">Refresh</button>
      </div>
    </div>

    <section v-if="manuscriptExport" class="export-output">
      <div class="panel-header compact">
        <div>
          <p class="eyebrow">{{ manuscriptExport.scene_count }} scenes</p>
          <h4>{{ manuscriptExport.title }}</h4>
        </div>
        <small>{{ manuscriptExport.generated_at }}</small>
      </div>
      <pre>{{ manuscriptExport.content }}</pre>
    </section>

    <div class="accepted-list">
      <article v-for="scene in manuscriptScenes" :key="scene.id" class="accepted-item">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">
              {{ chapterTitleForScene(scene.scene_id) }} / Version {{ scene.version }}
            </p>
            <h4>{{ scene.title }}</h4>
          </div>
          <div class="revision-actions">
            <small>{{ scene.accepted_at }}</small>
            <div class="button-row">
              <button
                v-if="editingManuscriptSceneId !== scene.scene_id"
                class="secondary"
                type="button"
                @click="startEditingManuscriptScene(scene)"
              >
                Edit
              </button>
            </div>
          </div>
        </div>
        <form
          v-if="editingManuscriptSceneId === scene.scene_id"
          class="manuscript-edit"
          @submit.prevent="saveManuscriptSceneEdit(scene.scene_id)"
        >
          <label>
            <span>Title</span>
            <input v-model="manuscriptEditTitle" autocomplete="off" />
          </label>
          <label>
            <span>Content</span>
            <textarea v-model="manuscriptEditContent" rows="14" />
          </label>
          <div class="form-actions artifact-actions">
            <p class="save-state">Saving creates a new manuscript revision.</p>
            <div class="button-row">
              <button class="secondary" type="button" @click="cancelEditingManuscriptScene">
                Cancel
              </button>
              <button class="primary" type="submit" :disabled="isSavingManuscriptScene">
                {{ isSavingManuscriptScene ? 'Saving...' : 'Save Version' }}
              </button>
            </div>
          </div>
        </form>
        <pre v-else>{{ scene.content }}</pre>
      </article>
      <p v-if="manuscriptScenes.length === 0" class="empty-state">
        No accepted manuscript scenes yet.
      </p>
    </div>
  </section>
</template>
