<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useProposalDraftStore } from '../../stores/proposalDraft'
const draft = useProposalDraftStore()
const dialog = ref<HTMLDialogElement>()
let opener: HTMLElement | null = null
watch(() => draft.leavePending, async (pending) => {
  await nextTick()
  if (pending) { opener = document.activeElement as HTMLElement; dialog.value?.showModal() }
  else { dialog.value?.close(); if (opener?.isConnected) opener.focus() }
})
</script>
<template>
  <dialog ref="dialog" class="app-dialog" aria-labelledby="proposal-leave-title" aria-describedby="proposal-leave-description"
    @cancel.prevent="draft.resolveLeave('cancel')">
    <header class="dialog-heading"><h2 id="proposal-leave-title">保存草稿后离开？</h2></header>
    <div class="dialog-content">
      <p id="proposal-leave-description">不保存将丢弃本次未提交修改。保存仅暂存到本机，不会接受为正式正文。</p>
      <p v-if="draft.leaveError" class="error" role="alert">{{ draft.leaveError }}</p>
      <div class="button-row">
        <button type="button" class="primary" @click="draft.resolveLeave('save')">保存草稿并离开</button>
        <button type="button" class="secondary danger" @click="draft.resolveLeave('discard')">不保存并离开</button>
        <button type="button" class="secondary" autofocus @click="draft.resolveLeave('cancel')">取消</button>
      </div>
    </div>
  </dialog>
</template>
