<script setup lang="ts">
import { useManuscriptStore } from '../../stores/manuscript'
import SaveState from '../ui/SaveState.vue'
const store = useManuscriptStore()
const memberOf = (chapter: string) => store.manuscriptVolumes.find(volume => volume.chapter_ids.includes(chapter))?.id ?? ''
function selectVolume(event: Event) {
  const select = event.target as HTMLSelectElement
  store.selectVolume(select.value)
  select.value = store.activeVolumeId
}
async function assign(event: Event, chapter: string) {
  const select = event.target as HTMLSelectElement
  await store.assignChapterVolume(chapter, select.value)
  select.value = memberOf(chapter)
}
</script>

<template>
  <section class="volume-manager" aria-label="卷组织">
    <div class="panel-header"><h3>卷组织</h3><button type="button" class="secondary" :disabled="store.isLoadingVolumes || store.isSavingVolume" @click="store.loadManuscriptVolumes()">刷新卷目录</button></div>
    <p>卷只组织章节；移动章节不会改变场景的叙事时点或正文版本。</p>
    <label><span>选择卷</span><select :value="store.activeVolumeId" aria-label="选择卷" :disabled="store.isSavingVolume" @change="selectVolume">
      <option value="">新建卷</option><option v-for="volume in store.manuscriptVolumes" :key="volume.id" :value="volume.id">{{ volume.sequence }} · {{ volume.title }}</option>
    </select></label>
    <p v-if="!store.manuscriptVolumes.length" class="empty-state">尚未分卷。现有章节仍保留，可以先创建空卷。</p>
    <form class="scene-fields" @submit.prevent="store.saveVolume()">
      <label><span>卷名</span><input v-model="store.volumeDraft.title" aria-label="卷名" maxlength="160" :disabled="store.isSavingVolume" /></label>
      <label><span>卷排序号</span><input v-model.number="store.volumeDraft.sequence" aria-label="卷排序号" type="number" min="1" max="999" :disabled="store.isSavingVolume" /></label>
      <div class="button-row">
        <button type="submit" class="primary" :disabled="store.isSavingVolume">{{ store.isSavingVolume ? '保存中…' : '保存卷' }}</button>
        <button v-if="store.activeVolumeId" type="button" class="secondary danger" :disabled="store.isSavingVolume" @click="store.deleteVolume()">删除卷，保留章节</button>
      </div>
    </form>
    <SaveState :scope="store.volumeScopeKey()" :saving="store.isSavingVolume" :error="store.volumeError" />
    <p v-if="store.volumeError" role="alert" class="error-text">{{ store.volumeError }}</p>
    <p v-else-if="store.volumeStatus" role="status">{{ store.volumeStatus }}</p>
    <details><summary>章节归卷（保存后立即生效）</summary>
      <p v-if="!store.manuscriptChapters.length" class="empty-state">还没有章节，请在下方创建。空卷会保留。</p>
      <label v-for="chapter in store.manuscriptChapters" :key="chapter.id"><span>{{ chapter.sequence }} · {{ chapter.title }}</span>
        <select :value="memberOf(chapter.id)" :aria-label="`章节《${chapter.title}》所属卷`" :disabled="store.isSavingVolume" @change="assign($event, chapter.id)">
          <option value="">未分卷</option><option v-for="volume in store.manuscriptVolumes" :key="volume.id" :value="volume.id">{{ volume.sequence }} · {{ volume.title }}</option>
        </select>
      </label>
    </details>
  </section>
</template>
