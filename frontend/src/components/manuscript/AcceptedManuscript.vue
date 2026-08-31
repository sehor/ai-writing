<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useManuscriptStore } from '../../stores/manuscript'

const store = useManuscriptStore()
const {
  manuscriptScenes,
  editingManuscriptSceneId,
  isSavingManuscriptScene,
  isExportingManuscript,
  manuscriptEditTitle,
  manuscriptEditContent,
  manuscriptEditVersion,
  manuscriptEditNeedsReview,
  manuscriptEditReviewReady,
  isRefreshingManuscriptEdit,
  manuscriptError,
  manuscriptExport,
} = storeToRefs(store)
const {
  loadManuscriptScenes,
  exportManuscript,
  startEditingManuscriptScene,
  cancelEditingManuscriptScene,
  saveManuscriptSceneEdit,
  refreshManuscriptEditConflict,
  rebaseManuscriptSceneEdit,
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
                :disabled="isSavingManuscriptScene"
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
            <input v-model="manuscriptEditTitle" autocomplete="off" :disabled="isSavingManuscriptScene" />
          </label>
          <label>
            <span>Content</span>
            <textarea v-model="manuscriptEditContent" rows="14" :disabled="isSavingManuscriptScene" />
          </label>
          <p v-if="manuscriptError" class="error-text" role="alert">{{ manuscriptError }}</p>
          <section v-if="manuscriptEditNeedsReview" class="export-output" aria-label="正文版本冲突">
            <p class="error-text">
              编辑基于 {{ manuscriptEditVersion === null ? '未知版本（旧本地草稿）' : `v${manuscriptEditVersion}` }}。
              编辑内容已保留，请对照当前正文修改后再确认；确认不会自动保存。
            </p>
            <template v-if="manuscriptEditReviewReady">
              <h4>当前正文 v{{ scene.version }}：{{ scene.title }}</h4>
              <pre>{{ scene.content }}</pre>
              <button class="secondary" type="button" :disabled="isSavingManuscriptScene || isRefreshingManuscriptEdit" @click="rebaseManuscriptSceneEdit">
                已核对当前正文，保留我的编辑
              </button>
            </template>
            <button class="secondary" type="button" :disabled="isRefreshingManuscriptEdit || isSavingManuscriptScene" @click="refreshManuscriptEditConflict">
              {{ isRefreshingManuscriptEdit ? '读取中…' : '重新读取当前正文' }}
            </button>
          </section>
          <div class="form-actions artifact-actions">
            <p class="save-state">Saving creates a new manuscript revision.</p>
            <div class="button-row">
              <button class="secondary" type="button" :disabled="isSavingManuscriptScene" @click="cancelEditingManuscriptScene">
                Cancel
              </button>
              <button class="primary" type="submit" :disabled="isSavingManuscriptScene || manuscriptEditNeedsReview">
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
