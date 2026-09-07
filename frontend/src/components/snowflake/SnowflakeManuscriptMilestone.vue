<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useManuscriptStore } from '../../stores/manuscript'
import { storeToRefs } from 'pinia'
import { useSnowflakeStore } from '../../stores/snowflake'
import { useProjectContextStore } from '../../stores/projectContext'

const snowflake = useSnowflakeStore()
const { activeStepNumber } = storeToRefs(useProjectContextStore())

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ openManuscript: [] }>()
const { activeProjectId } = storeToRefs(useProjectContextStore())
const { revisions, manuscriptProgress } = storeToRefs(snowflake)
const manuscript = useManuscriptStore()
const { sceneContracts } = storeToRefs(manuscript)
const legacySource = ref<HTMLTextAreaElement | null>(null)
const legacyImportSceneId = ref('')
const legacyImportTitle = ref('')
const legacyImportContent = ref('')
const legacyImportError = ref('')
const legacyImportStatus = ref('')
const isImportingLegacy = ref(false)

const legacyStep10Revision = computed(() =>
  revisions.value.find((revision) => revision.status === 'legacy_draft')
)

watch(
  () => [activeProjectId.value, activeStepNumber.value],
  ([projectId, stepNumber]) => {
    if (projectId && stepNumber === 10) void manuscript.refreshSceneContracts(String(projectId))
  },
  { immediate: true },
)

function captureLegacySelection() {
  const source = legacySource.value
  if (!source || source.selectionStart === source.selectionEnd) return
  legacyImportContent.value = source.value.slice(source.selectionStart, source.selectionEnd).trim()
  legacyImportError.value = ''
  legacyImportStatus.value = 'Selection captured. Choose its Scene Contract and import it for review.'
}

function updateLegacyImportTitle() {
  const scene = sceneContracts.value.find((item) => item.id === legacyImportSceneId.value)
  if (scene) legacyImportTitle.value = scene.title
}

async function importLegacySelection() {
  if (!legacyStep10Revision.value) return
  legacyImportError.value = ''
  legacyImportStatus.value = ''
  isImportingLegacy.value = true
  try {
    await snowflake.importLegacyDraftSelection(
      legacyStep10Revision.value.id,
      legacyImportSceneId.value,
      legacyImportTitle.value,
      legacyImportContent.value,
    )
    legacyImportStatus.value = 'Pending Manuscript proposal created. Open Manuscript to review it.'
    legacyImportContent.value = ''
  } catch (error) {
    legacyImportError.value = error instanceof Error ? error.message : 'Could not import selection.'
  } finally {
    isImportingLegacy.value = false
  }
}
</script>

<template>
<section
  v-if="visible"
  class="artifact-editor manuscript-milestone"
  aria-labelledby="manuscript-milestone-title"
>
  <div>
    <h3 id="manuscript-milestone-title">进入正文写作流程</h3>
    <p>正文统一在写作工作台中管理。根据场景契约生成草稿，审核接受后保存为正文版本。</p>
    <dl v-if="manuscriptProgress" class="milestone-stats">
      <div><dt>场景契约</dt><dd>{{ manuscriptProgress.total_scene_contracts }}</dd></div>
      <div><dt>待审核建议</dt><dd>{{ manuscriptProgress.pending_manuscript_proposals }}</dd></div>
      <div><dt>已接受版本</dt><dd>{{ manuscriptProgress.accepted_latest_revisions }}</dd></div>
      <div><dt>需更新场景</dt><dd>{{ manuscriptProgress.stale_scene_count }}</dd></div>
      <div><dt>完成情况</dt><dd>{{ manuscriptProgress.completion_percent }}%</dd></div>
    </dl>
    <details v-if="legacyStep10Revision" class="legacy-manuscript">
      <summary>旧版第十步草稿 · 只读</summary>
      <p>旧版草稿已保留，但尚未接受。选择下方正文片段，导入目标场景后再审核。</p>
      <textarea
        ref="legacySource"
        :value="legacyStep10Revision.content"
        rows="10"
        readonly
        aria-label="Preserved legacy Step 10 draft"
        @select="captureLegacySelection"
      />
      <div class="legacy-import-form">
        <label>
          <span>目标场景</span>
          <select v-model="legacyImportSceneId" @change="updateLegacyImportTitle">
            <option value="">选择场景</option>
            <option v-for="scene in sceneContracts" :key="scene.id" :value="scene.id">
              {{ scene.sequence }}. {{ scene.title }}
            </option>
          </select>
        </label>
        <label>
          <span>草稿标题</span>
          <input v-model="legacyImportTitle" maxlength="160" />
        </label>
        <label>
          <span>选中的旧版正文</span>
          <textarea v-model="legacyImportContent" rows="6" readonly />
        </label>
        <p v-if="legacyImportError" class="error">{{ legacyImportError }}</p>
        <p v-else-if="legacyImportStatus" class="save-state">{{ legacyImportStatus }}</p>
        <button
          class="secondary"
          type="button"
          :disabled="
            isImportingLegacy ||
            !legacyImportSceneId ||
            !legacyImportTitle.trim() ||
            !legacyImportContent
          "
          @click="importLegacySelection"
        >
          {{ isImportingLegacy ? 'Importing...' : '导入选文并审核' }}
        </button>
      </div>
    </details>
  </div>
  <button class="primary" type="button" @click="emit('openManuscript')">进入正文写作</button>
</section>
</template>

<style scoped>
.manuscript-milestone {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
}

.milestone-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  margin: 1rem 0 0;
}

.milestone-stats div {
  display: grid;
  gap: 0.25rem;
}

.milestone-stats dt {
  color: var(--text-muted, var(--muted));
  font-size: 0.8rem;
}

.milestone-stats dd {
  margin: 0;
  font-weight: 700;
}

.legacy-import-form {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

@media (max-width: 48rem) {
  .manuscript-milestone {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
</style>
