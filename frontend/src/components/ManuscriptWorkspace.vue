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
    <ManuscriptInputs />
    <ReferenceWorkspace />
    <ManuscriptProposalWorkspace />
    <AcceptedManuscript />
    <RevisionHistory />
    <WritebackReview />
  </section>
</template>
