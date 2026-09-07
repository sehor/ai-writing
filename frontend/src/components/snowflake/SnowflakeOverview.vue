<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useSnowflakeStore } from '../../stores/snowflake'
import { useProjectContextStore } from '../../stores/projectContext'

const snowflake = useSnowflakeStore()
const { activeStepNumber } = storeToRefs(useProjectContextStore())

const emit = defineEmits<{ openStep: [stepNumber: number] }>()
const { steps, stepStates } = storeToRefs(snowflake)
function stateFor(stepNumber: number) {
  return stepStates.value.find((item) => item.step.number === stepNumber)
}

function stepStateLabel(stepNumber: number): string {
  const state = stateFor(stepNumber)
  if (!state) return 'Missing'
  if (state.pending_count > 0) return `${state.pending_count} pending`
  if (state.state === 'approved') return 'Approved'
  if (state.state === 'stale') return 'Needs review'
  if (state.state === 'skipped') return 'Skipped'
  return 'Missing'
}
</script>

<template>
<section class="pipeline">
  <div class="panel-header">
    <div>
      <h3>雪花法</h3>
    </div>
    <span class="step-chip">
      {{ stepStates.filter((item) => item.state === 'approved').length }} approved
    </span>
  </div>

  <ol class="steps">
    <li
      v-for="step in steps"
      :key="step.number"
      :class="{
        current: step.number === activeStepNumber,
        saved: stateFor(step.number)?.state === 'approved',
        stale: stateFor(step.number)?.state === 'stale',
        pending: (stateFor(step.number)?.pending_count ?? 0) > 0,
      }"
    >
      <button
        class="step-selector"
        type="button"
        :aria-label="`Open step ${step.number}: ${step.title}`"
        :aria-current="step.number === activeStepNumber ? 'step' : undefined"
        @click="emit('openStep', step.number)"
      >
        <span class="step-number">{{ step.number }}</span>
        <span class="step-copy">
          <span class="step-heading">
            <strong>{{ step.title }}</strong>
            <span
              :class="stateFor(step.number)?.state === 'approved' ? 'selected-step-label' : 'open-step-label'"
            >{{ stepStateLabel(step.number) }}</span>
          </span>
          <span>{{ step.description }}</span>
          <code>{{ step.artifact }}</code>
        </span>
      </button>
    </li>
  </ol>
</section>
</template>

<style scoped>
.steps li.stale {
  border-color: var(--warning);
  box-shadow: inset 3px 0 0 var(--warning);
}

.steps li.pending {
  border-style: dashed;
}
</style>
