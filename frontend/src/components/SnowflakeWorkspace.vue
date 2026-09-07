<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useSnowflakeStore } from '../stores/snowflake'
import SnowflakeOverview from './snowflake/SnowflakeOverview.vue'
import SnowflakeArtifactEditor from './snowflake/SnowflakeArtifactEditor.vue'
import SnowflakeManuscriptMilestone from './snowflake/SnowflakeManuscriptMilestone.vue'
import SnowflakeCompilerReview from './snowflake/SnowflakeCompilerReview.vue'
import SnowflakeRevisionHistory from './snowflake/SnowflakeRevisionHistory.vue'
import SnowflakeRecords from './snowflake/SnowflakeRecords.vue'

const workspace = useWorkspaceStore()
const { activeStepNumber, activeStep, activeProject } = storeToRefs(workspace)
const { steps } = storeToRefs(useSnowflakeStore())
const isStepWorkspaceOpen = ref(false)
const isRecordStep = computed(() => activeStepNumber.value >= 6 && activeStepNumber.value <= 9)
function openStep(stepNumber: number) {
  workspace.selectStep(stepNumber)
  isStepWorkspaceOpen.value = true
}
function moveStep(offset: number) {
  const nextStep = steps.value.find(step => step.number === activeStepNumber.value + offset)
  if (nextStep) workspace.selectStep(nextStep.number)
}
</script>

<template>
  <SnowflakeOverview v-if="!isStepWorkspaceOpen" @open-step="openStep" />
<section v-else class="step-workspace-header" aria-labelledby="step-workspace-title">
  <button class="secondary back-to-steps" type="button" @click="isStepWorkspaceOpen = false">返回规划总览</button>
  <div class="step-workspace-title">
    <p class="eyebrow">雪花法 · 第 {{ activeStepNumber }} / {{ steps.length }} 步</p>
    <h3 id="step-workspace-title">{{ activeStep?.title ?? '雪花步骤' }}</h3>
    <p>{{ activeStep?.description }}</p>
  </div>
  <div class="step-navigation" aria-label="Step navigation">
    <button
      class="secondary"
      type="button"
      :disabled="activeStepNumber <= 1"
      @click="moveStep(-1)"
    >上一步</button>
    <button
      class="secondary"
      type="button"
      :disabled="activeStepNumber >= steps.length"
      @click="moveStep(1)"
    >下一步</button>
  </div>
</section>

  <!-- Keep the importer instance alive while navigating, as its draft belongs to this workspace. -->
  <SnowflakeManuscriptMilestone
    :visible="isStepWorkspaceOpen && !!activeStep?.virtual"
    @open-manuscript="workspace.activeSection = 'manuscript'"
  />
  <template v-if="isStepWorkspaceOpen">
    <SnowflakeArtifactEditor v-if="!activeStep?.virtual" :active-step="activeStep" :has-project="!!activeProject" />
    <SnowflakeRevisionHistory v-if="!activeStep?.virtual && !isRecordStep" :key="activeStepNumber" />
    <SnowflakeRecords v-if="isRecordStep" :key="`records-${activeStepNumber}`" />
    <SnowflakeCompilerReview v-if="activeStepNumber === 7 || activeStepNumber === 8" :has-project="!!activeProject" />
  </template>
</template>
