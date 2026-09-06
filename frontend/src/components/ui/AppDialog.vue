<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
defineProps<{ title: string }>()
const dialog = ref<HTMLDialogElement>()
const emit = defineEmits<{ close: [] }>()
let opener: HTMLElement | null = null
function open() {
  opener = document.activeElement as HTMLElement
  dialog.value?.showModal()
}
function close() {
  dialog.value?.close()
}
function closed() {
  opener?.focus()
  emit('close')
}
defineExpose({ open, close })
</script>
<template>
  <dialog ref="dialog" class="app-dialog" :aria-label="title" @close="closed">
    <header class="dialog-heading">
      <h2>{{ title }}</h2>
      <button
        type="button"
        class="icon-button"
        aria-label="关闭"
        @click="close"
      >
        <AppIcon name="close" />
      </button>
    </header>
    <div class="dialog-content"><slot /></div>
  </dialog>
</template>
