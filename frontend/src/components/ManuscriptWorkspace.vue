<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useManuscriptStore } from '../stores/manuscript'
import { useWorkspaceStore } from '../stores/workspace'
import { useProposalDraftStore } from '../stores/proposalDraft'
import { useAppearanceStore } from '../stores/appearance'
import { organizeManuscript } from '../domain/manuscriptOrganization'
import { confirmLeave } from '../composables/useDirtyGuard'
import { isScopeDirty, persistDraft } from '../services/draftSessions'
import AppIcon from './ui/AppIcon.vue'
import EmptyState from './ui/EmptyState.vue'
import AcceptedManuscript from './manuscript/AcceptedManuscript.vue'
import ManuscriptInputs from './manuscript/ManuscriptInputs.vue'
import ManuscriptProposalWorkspace from './manuscript/ManuscriptProposalWorkspace.vue'
import ReferenceWorkspace from './manuscript/ReferenceWorkspace.vue'
import { useCopilotContextStore } from '../stores/copilotContext'
import RevisionHistory from './manuscript/RevisionHistory.vue'
import WritebackReview from './manuscript/WritebackReview.vue'
const store = useManuscriptStore()
const workspace = useWorkspaceStore()
const draft = useProposalDraftStore()
const appearance = useAppearanceStore()
const search = ref('')
const directoryOpen = ref(false)
const view = ref<'manuscript' | 'proposal'>('manuscript')
const panel = ref<'reference' | 'settings' | 'history' | 'analysis' | null>(
  null,
)
const panelButtons = ref<HTMLElement>()
const panelEl = ref<HTMLElement>()
const copilot = useCopilotContextStore()
watch(() => copilot.captureCount, () => { if (panel.value !== 'reference') openPanel('reference') })
const current = computed(() =>
  store.manuscriptScenes.find(
    (scene) => scene.scene_id === store.activeSceneId,
  ),
)
const pending = computed(() =>
  store.manuscriptProposals.filter(
    (p) => p.scene_id === store.activeSceneId && p.status === 'pending_review',
  ),
)
const volumeGroups = computed(() => organizeManuscript(store.manuscriptVolumes, store.manuscriptChapters, store.sceneContracts, search.value))
const currentTitle = computed(
  () => store.activeSceneContract?.title ?? '正文写作',
)
let restoringSelection = false
function allowDraftLeave() {
  if (draft.dirty && !confirmLeave(draft.scopeKey, 'AI 草稿')) return false
  draft.persist()
  return true
}
async function selectScene(id: string) {
  if (id === store.activeSceneId) {
    directoryOpen.value = false
    return
  }
  store.activeSceneId = id
  await nextTick()
  if (store.activeSceneId !== id) return
  directoryOpen.value = false
}
watch(
  () => [
    workspace.activeProjectId,
    store.activeSceneId,
    current.value?.scene_id,
  ],
  (_, previous) => {
    if (workspace.isLoadingProject) return
    if (restoringSelection) {
      restoringSelection = false
      return
    }
    const changedScene =
      previous?.[0] === workspace.activeProjectId &&
      previous?.[1] &&
      previous[1] !== store.activeSceneId
    function rollback() {
      restoringSelection = true
      store.activeSceneId = previous?.[1] ?? ''
    }
    if (changedScene && !allowDraftLeave()) {
      rollback()
      return
    }
    const scene = current.value
    if (scene && store.editingManuscriptSceneId !== scene.scene_id) {
      store.startEditingManuscriptScene(scene)
      if (store.editingManuscriptSceneId !== scene.scene_id) {
        rollback()
        return
      }
    } else if (!scene && changedScene && store.editingManuscriptSceneId) {
      const key = store.manuscriptEditScopeKey()
      const edits = store.currentManuscriptEdits()
      if (isScopeDirty(key, edits)) {
        if (!confirmLeave(key, '正文编辑')) {
          rollback()
          return
        }
        persistDraft(key, edits)
      }
      store.cancelEditingManuscriptScene()
    }
    view.value = scene
      ? 'manuscript'
      : pending.value.length
        ? 'proposal'
        : 'manuscript'
    const proposal =
      pending.value[0] ??
      store.manuscriptProposals.find((p) => p.scene_id === store.activeSceneId)
    if (proposal) store.activeProposalId = proposal.id
  },
  { immediate: true },
)
watch(
  () => workspace.isLoadingProject,
  (loading) => {
    if (loading) return
    if (
      current.value &&
      store.editingManuscriptSceneId !== current.value.scene_id
    )
      store.startEditingManuscriptScene(current.value)
    view.value = current.value
      ? 'manuscript'
      : pending.value.length
        ? 'proposal'
        : 'manuscript'
    if (pending.value[0]) store.activeProposalId = pending.value[0].id
  },
)
watch(
  () => store.isCreatingProposal || store.isCreatingProviderProposal,
  (creating, before) => {
    if (before && !creating && pending.value.length) {
      view.value = 'proposal'
      panel.value = null
    }
  },
)
watch(
  () => store.activeProposal?.status,
  (status, before) => {
    if (status === 'accepted' && before === 'pending_review')
      view.value = 'manuscript'
  },
)
function switchView(next: typeof view.value) {
  if (next === view.value || (view.value === 'proposal' && !allowDraftLeave()))
    return
  view.value = next
}
async function openPanel(next: typeof panel.value) {
  panel.value = panel.value === next ? null : next
  await nextTick()
  if (panel.value) panelEl.value?.focus()
  else panelButtons.value?.querySelector<HTMLButtonElement>('button')?.focus()
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing || document.querySelector('dialog[open]')) return
  if (event.key === 'Escape') {
    if (panel.value) void openPanel(panel.value)
    else if (directoryOpen.value) directoryOpen.value = false
    else appearance.focus = false
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    if (view.value === 'proposal') draft.persist()
    else if (current.value)
      void store.saveManuscriptSceneEdit(current.value.scene_id)
  }
}
onMounted(() => window.addEventListener('keydown', keydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', keydown)
  appearance.focus = false
})
</script>
<template>
  <section
    class="writing-workspace"
    :class="{ 'has-inspector': panel, 'is-focused': appearance.focus }"
  >
    <aside
      class="chapter-directory"
      :class="{ 'directory-open': directoryOpen }"
      aria-label="章节目录"
    >
      <header class="directory-heading">
        <h2>章节目录</h2>
        <button
          class="icon-button"
          aria-label="章节与场景设置"
          @click="openPanel('settings')"
        >
          <AppIcon name="plus" />
        </button>
      </header>
      <label class="directory-search"
        ><AppIcon name="search" :size="16" /><input
          v-model="search"
          aria-label="搜索章节与场景"
          placeholder="查找章节或场景"
      /></label>
      <div class="chapter-groups">
        <p v-if="store.volumeError" class="error-text" role="alert">{{ store.volumeError }}<button type="button" class="quiet-button" @click="store.loadManuscriptVolumes()">重试卷目录</button></p>
        <details v-for="volume in volumeGroups" :key="volume.id" class="volume-group" :data-volume-id="volume.id" open>
          <summary>{{ volume.title }}</summary>
          <p v-if="!volume.groups.length" class="empty-state">空卷 · 在章节与场景设置中归入章节</p>
        <details
          v-for="group in volume.groups"
          :key="group.id"
          class="chapter-group"
          open
        >
          <summary>
            {{ group.title }}<small>{{ group.scenes.length }}</small>
          </summary>
          <button
            v-for="scene in group.scenes"
            :key="scene.id"
            class="scene-link"
            :class="{ active: store.activeSceneId === scene.id }"
            :aria-current="
              store.activeSceneId === scene.id ? 'true' : undefined
            "
            @click="selectScene(scene.id)"
          >
            <span>{{ scene.title }}<small v-if="store.manuscriptScenes.some(m => m.scene_id === scene.id) && (scene.manuscript_plan_version ?? 0) < (scene.plan_version ?? 1)">规划已更新，正文待核对</small></span
            ><small
              v-if="
                store.manuscriptProposals.some(
                  (p) =>
                    p.scene_id === scene.id && p.status === 'pending_review',
                )
              "
              >待审</small
            >
          </button>
        </details>
        </details>
        <p v-if="!volumeGroups.length" class="empty-state">
          {{ search ? '没有找到匹配的章节或场景。' : '故事从第一个场景开始。' }}
        </p>
      </div>
      <button
        class="quiet-button directory-settings"
        @click="openPanel('settings')"
      >
        <AppIcon name="settings" />管理章节与场景
      </button>
    </aside>
    <button
      v-if="directoryOpen"
      class="directory-scrim"
      aria-label="收起章节目录"
      @click="directoryOpen = false"
    ></button>
    <section class="writing-main" aria-label="当前场景写作">
      <header class="writing-toolbar">
        <div class="writing-title">
          <button
            class="icon-button directory-toggle"
            aria-label="展开章节目录"
            @click="directoryOpen = !directoryOpen"
          >
            <AppIcon name="book" /></button
          ><span>{{ currentTitle }}</span>
        </div>
        <div class="writing-tools">
          <label class="font-picker"
            ><span class="sr-only">正文字号</span
            ><select v-model.number="appearance.fontSize" aria-label="正文字号">
              <option
                v-for="size in [16, 18, 20, 22]"
                :key="size"
                :value="size"
              >
                {{ size }} px
              </option>
            </select></label
          ><button
            class="icon-button"
            :aria-label="appearance.focus ? '退出专注模式' : '进入专注模式'"
            :aria-pressed="appearance.focus"
            :title="appearance.focus ? '退出专注模式' : '进入专注模式'"
            @click="appearance.focus = !appearance.focus"
          >
            <AppIcon name="focus" />
          </button>
        </div>
      </header>
      <div class="writing-subbar">
        <nav class="segmented-control" aria-label="写作视图">
          <button
            :aria-pressed="view === 'manuscript'"
            :class="{ active: view === 'manuscript' }"
            @click="switchView('manuscript')"
          >
            正式正文</button
          ><button
            :aria-pressed="view === 'proposal'"
            :class="{ active: view === 'proposal' }"
            @click="switchView('proposal')"
          >
            待审核草稿<span v-if="pending.length" class="count">{{
              pending.length
            }}</span>
          </button>
        </nav>
        <button class="quiet-button" @click="openPanel('settings')">
          生成草稿
        </button>
      </div>
      <div class="editor-scroll">
        <AcceptedManuscript
          v-if="view === 'manuscript' && current"
          :scene-id="store.activeSceneId"
        /><ManuscriptProposalWorkspace
          v-else-if="view === 'proposal'"
          :scene-id="store.activeSceneId"
        /><EmptyState
          v-else
          :title="
            store.activeSceneId
              ? '这一幕，等待落笔'
              : '选择一个场景，继续你的故事'
          "
          :description="
            store.activeSceneId
              ? '根据场景设置生成草稿，审核接受后即可在这里持续写作。'
              : '从左侧选择场景，或先建立章节与场景设置。'
          "
          icon="feather"
          ><button class="primary" @click="openPanel('settings')">
            {{ store.activeSceneId ? '打开场景设置' : '建立章节与场景' }}
          </button></EmptyState
        >
      </div>
      <footer ref="panelButtons" class="writing-footer">
        <span class="keyboard-hint"
          >Ctrl S · {{ view === 'proposal' ? '暂存草稿' : '保存版本' }}</span
        >
        <div class="context-actions">
          <button
            :class="{ active: panel === 'reference' }"
            @click="openPanel('reference')"
          >
            参考资料</button
          ><button
            :class="{ active: panel === 'history' }"
            @click="openPanel('history')"
          >
            版本历史</button
          ><button
            :class="{ active: panel === 'analysis' }"
            @click="openPanel('analysis')"
          >
            分析与回写
          </button>
        </div>
      </footer>
    </section>
    <aside
      v-if="panel"
      ref="panelEl"
      tabindex="-1"
      class="writing-inspector"
      aria-label="写作辅助面板"
    >
      <header class="inspector-heading">
        <h2>
          {{
            {
              reference: '参考资料',
              settings: '章节与场景设置',
              history: '版本历史',
              analysis: '分析与回写',
            }[panel]
          }}
        </h2>
        <button
          class="icon-button"
          aria-label="关闭辅助面板"
          @click="openPanel(panel)"
        >
          <AppIcon name="close" />
        </button>
      </header>
      <div class="inspector-body">
        <ReferenceWorkspace v-if="panel === 'reference'" /><ManuscriptInputs
          v-if="panel === 'settings'"
        /><RevisionHistory v-if="panel === 'history'" /><WritebackReview
          v-if="panel === 'analysis'"
        />
      </div>
    </aside>
  </section>
</template>
