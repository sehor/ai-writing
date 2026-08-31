<script setup lang="ts">
import AcceptedManuscript from './manuscript/AcceptedManuscript.vue'
import ManuscriptInputs from './manuscript/ManuscriptInputs.vue'
import ManuscriptProposalWorkspace from './manuscript/ManuscriptProposalWorkspace.vue'
import ReferenceWorkspace from './manuscript/ReferenceWorkspace.vue'
import RevisionHistory from './manuscript/RevisionHistory.vue'
import WritebackReview from './manuscript/WritebackReview.vue'
</script>

<template>
  <section class="manuscript-workspace">
    <details class="manuscript-setup" open>
      <summary>章节与场景设置 · 写作时可收起</summary>
      <ManuscriptInputs />
    </details>
    <div class="writing-desk">
      <section class="writing-desk-editor" aria-label="正文与作者草稿">
        <ManuscriptProposalWorkspace />
        <AcceptedManuscript />
      </section>
      <aside class="writing-desk-context" aria-label="写作参考">
        <ReferenceWorkspace />
      </aside>
    </div>
    <section class="writing-desk-review" aria-label="版本与待审核变更">
      <RevisionHistory />
      <WritebackReview />
    </section>
  </section>
</template>

<style scoped>
.manuscript-setup { border-bottom: 1px solid #d9dfe5; padding-bottom: 16px; }
.manuscript-setup > summary { cursor: pointer; padding: 12px 0; font-weight: 600; }
.writing-desk { display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr); gap: 24px; align-items: start; }
.writing-desk-editor, .writing-desk-context, .writing-desk-review { min-width: 0; }
.writing-desk-context { border-left: 1px solid #d9dfe5; padding-left: 20px; }
.writing-desk-context :deep(.proposal-grid), .writing-desk-context :deep(.scene-fields) { grid-template-columns: minmax(0, 1fr); }
.writing-desk-editor :deep(.proposal-grid) { grid-template-columns: minmax(130px, 1fr) minmax(0, 3fr); }
.writing-desk-editor :deep(textarea) { width: 100%; box-sizing: border-box; line-height: 1.8; }
.writing-desk-editor :deep(.draft-comparison) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.writing-desk-review { border-top: 1px solid #d9dfe5; padding-top: 20px; }
@media (max-width: 1250px) {
  .writing-desk { grid-template-columns: minmax(0, 1fr); }
  .writing-desk-context { border-left: 0; padding-left: 0; }
}
@media (max-width: 700px) {
  .writing-desk-editor :deep(.proposal-grid), .writing-desk-editor :deep(.draft-comparison) { grid-template-columns: minmax(0, 1fr); }
}
</style>
