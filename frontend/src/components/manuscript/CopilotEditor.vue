<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { vAutosize } from '../../directives/autosize'
import { useCopilotContextStore, type EditorTarget } from '../../stores/copilotContext'

const props = defineProps<{ modelValue: string; target: EditorTarget; label: string; testId?: string; disabled?: boolean; unavailable?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const textarea = ref<HTMLTextAreaElement>()
const selected = ref(false)
const copilot = useCopilotContextStore()
let sessionId = crypto.randomUUID()
let identity = ''
watch(() => [props.target, props.modelValue, props.disabled, props.unavailable] as const, () => {
  const next = JSON.stringify(props.target)
  if (identity !== next) { copilot.release(sessionId); sessionId = crypto.randomUUID(); identity = next; selected.value = false }
  if (props.disabled || props.unavailable) copilot.release(sessionId)
  else copilot.register({ ...props.target, snapshot_text: props.modelValue, session_id: sessionId })
}, { immediate: true, deep: true, flush: 'sync' })
function update(event: Event) { emit('update:modelValue', (event.target as HTMLTextAreaElement).value) }
function selectionChanged() {
  selected.value = !!textarea.value && textarea.value.selectionEnd > textarea.value.selectionStart
}
function ask() {
  if (!textarea.value || props.disabled || props.unavailable) return
  copilot.register({ ...props.target, snapshot_text: props.modelValue, session_id: sessionId })
  copilot.capture(textarea.value.selectionStart, textarea.value.selectionEnd)
}
onBeforeUnmount(() => copilot.release(sessionId))
</script>

<template>
  <div class="copilot-editor">
    <div class="button-row">
      <button class="secondary" type="button" :disabled="disabled || unavailable || !modelValue.trim()" @click="ask">
        {{ selected ? '就选中文字求助' : '就整场景求助' }}
      </button>
      <small>打开参考面板后填写写作问题。</small>
    </div>
    <textarea ref="textarea" v-autosize class="prose-editor" :value="modelValue" :aria-label="label"
      :data-testid="testId" rows="18" maxlength="40000" spellcheck="false" :disabled="disabled"
      @input="update" @select="selectionChanged" @keyup="selectionChanged" @mouseup="selectionChanged" />
  </div>
</template>
