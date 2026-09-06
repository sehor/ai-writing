<script setup lang="ts">
import { computed } from 'vue'
import { vAutosize } from '../../directives/autosize'
import SaveState from '../ui/SaveState.vue'
import { storeToRefs } from 'pinia'
import { useManuscriptStore } from '../../stores/manuscript'

const props = defineProps<{ sceneId?: string }>()
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
const visibleScenes = computed(() => props.sceneId === undefined ? manuscriptScenes.value : manuscriptScenes.value.filter(scene => scene.scene_id === props.sceneId))
const characterCount = computed(() => manuscriptEditContent.value.replace(/\s/g, '').length)
</script>

<template>
  <section class="accepted-manuscript">
    <div class="panel-header manuscript-document-actions">
      <SaveState :scope="store.manuscriptEditScopeKey()" :saving="isSavingManuscriptScene" :conflict="manuscriptEditNeedsReview" :error="manuscriptError" :version="manuscriptEditVersion" />
      <div class="button-row">
        <button v-if="sceneId" class="primary" type="button" :disabled="isSavingManuscriptScene || manuscriptEditNeedsReview" @click="saveManuscriptSceneEdit(sceneId)">{{ isSavingManuscriptScene ? '保存中…' : '保存版本' }}</button>
        <button
          class="secondary"
          type="button"
          :disabled="isExportingManuscript"
          @click="exportManuscript"
        >
          {{ isExportingManuscript ? '导出中…' : '导出 Markdown' }}
        </button>
        <button class="secondary" type="button" @click="loadManuscriptScenes()">刷新</button>
      </div>
    </div>

    <section v-if="manuscriptExport" class="export-output">
      <div class="panel-header compact">
        <div>
          <p class="eyebrow">{{ manuscriptExport.scene_count }} 个场景</p>
          <h4>{{ manuscriptExport.title }}</h4>
        </div>
        <small>{{ manuscriptExport.generated_at }}</small>
      </div>
      <pre>{{ manuscriptExport.content }}</pre>
    </section>

    <div class="accepted-list">
      <article v-for="scene in visibleScenes" :key="scene.id" class="accepted-item">
        <div v-if="!sceneId" class="panel-header compact">
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
                编辑
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
            <span class="sr-only">正文标题</span>
            <input v-model="manuscriptEditTitle" class="document-title-input" aria-label="正文标题" autocomplete="off" />
          </label>
          <label>
            <span class="sr-only">正文内容</span>
            <textarea v-autosize v-model="manuscriptEditContent" class="prose-editor" aria-label="正文内容" rows="18" spellcheck="false" />
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
            <p class="save-state">{{ characterCount.toLocaleString() }} 字 · 每次保存创建一个版本</p>
            <div v-if="!sceneId" class="button-row">
              <button class="secondary" type="button" :disabled="isSavingManuscriptScene" @click="cancelEditingManuscriptScene">
                取消
              </button>
              <button class="primary" type="submit" :disabled="isSavingManuscriptScene || manuscriptEditNeedsReview">
                {{ isSavingManuscriptScene ? '保存中…' : '保存版本' }}
              </button>
            </div>
          </div>
        </form>
        <pre v-else>{{ scene.content }}</pre>
      </article>
      <p v-if="manuscriptScenes.length === 0" class="empty-state">
        暂无正式正文。接受草稿后即可继续编辑。
      </p>
    </div>
  </section>
</template>
