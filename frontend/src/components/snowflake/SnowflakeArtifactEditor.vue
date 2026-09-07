<script setup lang="ts">
import { computed } from 'vue'
import type { SnowflakeStep } from '../../types'
import { storeToRefs } from 'pinia'
import { useSnowflakeStore } from '../../stores/snowflake'
import { useProjectContextStore } from '../../stores/projectContext'

const snowflake = useSnowflakeStore()
const { activeStepNumber } = storeToRefs(useProjectContextStore())

defineProps<{ activeStep: SnowflakeStep | undefined; hasProject: boolean }>()
const {
  steps, isSavingArtifact, isGeneratingArtifact, artifactError, artifactDraft,
  generationInstruction, generationMode, previousArtifactsContextChars,
  activeRevision, activeStepState, workflowTrace, hasUnsavedArtifactChanges, artifactStateLabel,
} = storeToRefs(snowflake)
const { saveArtifact, generateArtifact, decideRevision, skipActiveStep } = snowflake
const isRecordStep = computed(
  () => activeStepNumber.value >= 6 && activeStepNumber.value <= 9
)

const acceptanceImpact = computed(() => {
  const affected = new Set<number>([activeStepNumber.value])
  let changed = true
  while (changed) {
    changed = false
    for (const step of steps.value) {
      if (!affected.has(step.number) && step.dependencies.some((dependency) => affected.has(dependency))) {
        affected.add(step.number)
        changed = true
      }
    }
  }
  affected.delete(activeStepNumber.value)
  return [...affected].sort((left, right) => left - right)
})
</script>

<template>
<section
  class="artifact-editor"
  aria-labelledby="artifact-editor-title"
>
  <div class="panel-header">
    <div>
      <p class="eyebrow">{{ isRecordStep ? '已确认记录' : '当前产物' }}</p>
      <h3 id="artifact-editor-title">
        Step {{ activeStep?.number ?? 1 }}: {{ activeStep?.title ?? '雪花步骤' }}
      </h3>
    </div>
    <span class="step-chip">{{ activeStep?.artifact ?? 'artifact' }}</span>
  </div>

  <textarea
    v-if="!isRecordStep"
    v-model="artifactDraft"
    rows="12"
    :disabled="!hasProject"
    :placeholder="`Write the ${activeStep?.artifact ?? 'artifact'} for the active project.`"
  />

  <details
    v-if="
      isRecordStep &&
      activeStepState?.accepted_revision &&
      activeStepState.accepted_revision.source !== 'derived'
    "
    class="legacy-manuscript"
  >
    <summary>保留的旧版产物 · 仅供参考</summary>
    <p>
      This historical blob is not an authoritative Step {{ activeStepNumber }} head.
      Convert the useful material into records below and accept those records before compiling.
    </p>
    <textarea
      :value="activeStepState.accepted_revision.content"
      rows="8"
      readonly
      aria-label="Preserved legacy Snowflake Artifact"
    />
  </details>

  <div class="generation-controls">
    <label class="generation-instruction">
      <span>写作指令</span>
      <textarea
        v-model="generationInstruction"
        rows="3"
        maxlength="4000"
        :disabled="!hasProject"
        :placeholder="
          isRecordStep
            ? '描述需要生成或修改的记录。'
            : '描述希望生成或修改的内容。当前已确认产物会单独保留。'
        "
      />
    </label>

    <details class="advanced-generation"><summary>高级生成设置</summary><label class="context-budget">
      <span>上游参考字数上限</span>
      <input
        v-model.number="previousArtifactsContextChars"
        type="number"
        min="1000"
        max="400000"
        step="1000"
        inputmode="numeric"
        :disabled="!hasProject"
        aria-describedby="snowflake-context-budget-help"
      />
      <small id="snowflake-context-budget-help">
        优先使用相关的上游已确认记录，剩余字数用于较早步骤的产物。
      </small>
    </label></details>

    <label class="generation-mode">
      <span>生成方式</span>
      <select v-model="generationMode" :disabled="!hasProject">
        <template v-if="isRecordStep">
          <option value="record_set">生成记录草稿</option>
          <option value="selection">修改所选已确认记录</option>
          <option value="continue">续写所选已确认记录</option>
        </template>
        <option v-else value="replace">生成修订草稿</option>
      </select>
      <small v-if="isRecordStep">生成结果会作为待审核的记录修订，接受后才会更新正式规划。</small>
    </label>
  </div>

  <div class="form-actions artifact-actions">
    <p v-if="artifactError" class="error">{{ artifactError }}</p>
    <p v-else class="save-state">
      {{ isRecordStep ? '接受下方记录修订后，步骤汇总将同步更新。' : artifactStateLabel }}
    </p>
    <p
      v-if="!isRecordStep && activeRevision && ['draft', 'pending_review'].includes(activeRevision.status) && acceptanceImpact.length"
      class="save-state"
    >
      Accepting this revision will mark downstream steps {{ acceptanceImpact.join(', ') }} for review.
    </p>
    <div class="button-row">
      <button
        class="secondary"
        type="button"
        :disabled="isGeneratingArtifact || !hasProject"
        @click="generateArtifact"
      >
        {{ isGeneratingArtifact ? '生成中…' : isRecordStep ? '生成记录建议' : '生成草稿' }}
      </button>
      <button
        v-if="!isRecordStep"
        class="primary"
        type="button"
        :disabled="isSavingArtifact || !hasUnsavedArtifactChanges"
        @click="saveArtifact"
      >
        {{ isSavingArtifact ? '保存中…' : '保存草稿版本' }}
      </button>
      <button
        v-if="!isRecordStep && activeRevision && ['draft', 'pending_review'].includes(activeRevision.status)"
        class="primary"
        type="button"
        :disabled="isSavingArtifact || hasUnsavedArtifactChanges"
        @click="decideRevision(activeRevision.id, 'accepted')"
      >接受修订</button>
      <button
        v-if="!isRecordStep && activeRevision && ['draft', 'pending_review'].includes(activeRevision.status)"
        class="secondary"
        type="button"
        :disabled="isSavingArtifact"
        @click="decideRevision(activeRevision.id, 'rejected')"
      >
        拒绝
      </button>
      <button
        v-if="activeStep?.optional && activeStepState?.state !== 'skipped'"
        class="secondary"
        type="button"
        :disabled="isSavingArtifact"
        @click="skipActiveStep"
      >跳过可选步骤</button>
    </div>
  </div>

  <ol v-if="workflowTrace.length" class="trace-list" aria-label="Workflow trace">
    <li v-for="trace in workflowTrace" :key="`${trace.stage}-${trace.agent_name}`">
      <span>{{ trace.stage }}</span>
      <strong>{{ trace.agent_name }}</strong>
      <small>{{ trace.status }}</small>
    </li>
  </ol>
</section>
</template>

<style scoped>
.generation-instruction {
  display: grid;
  gap: 0.5rem;
  font-weight: 600;
}

.generation-instruction textarea {
  min-height: 5rem;
  font-weight: 400;
}

.generation-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 20rem);
  gap: 1rem;
  align-items: start;
}

.context-budget small {
  color: var(--text-muted, var(--muted));
  font-weight: 400;
  line-height: 1.4;
}

@media (max-width: 760px) {
  .generation-controls {
    grid-template-columns: 1fr;
  }
}
</style>
