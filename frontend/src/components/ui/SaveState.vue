<script setup lang="ts">
import { computed } from 'vue'
import { useEditorSessionStore } from '../../stores/editorSession'
const props = defineProps<{
  scope: string
  saving?: boolean
  conflict?: boolean
  error?: string
  version?: number | null
}>()
const sessions = useEditorSessionStore()
const state = computed(() => sessions.draftState(props.scope))
const label = computed(() =>
  props.conflict
    ? '版本冲突 · 编辑已保留'
    : props.saving
      ? '保存中…'
      : props.error
        ? '保存失败 · 请重试'
        : state.value?.autosaveFailed
          ? '本机暂存失败 · 请保存版本'
          : state.value?.dirty
            ? state.value.lastAutosavedAt
              ? '已暂存本机 · 尚未保存版本'
              : '有未保存的修改'
            : props.version
              ? `已保存 · 版本 ${props.version}`
              : '暂无修改',
)
</script>
<template>
  <span
    class="save-indicator"
    role="status"
    :class="{ 'is-warning': conflict || error || state?.autosaveFailed }"
    >{{ label }}</span
  >
</template>
