<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ManuscriptProposal } from '../../types'
import { loadDraft, saveDraft } from '../../services/draftCache'

const props = defineProps<{ projectId: string; proposal: ManuscriptProposal }>()
type Decision = 'pending' | 'reviewed' | 'question'
const decisions = ref<Record<string, Decision>>({})
const saveFailed = ref(false)
const material = computed(() => props.proposal.generation_review?.material)
const scope = computed(() => `generation-review:${props.projectId}:${props.proposal.id}`)
const items = computed(() => {
  const data = material.value
  if (!data) return []
  return [
    ...data.new_fact_candidates.map((fact, index) => ({
      id: `fact:${index}`, title: `事实候选 ${index + 1}`,
      details: [['候选事实', fact.claim], ['引入理由', fact.reason_introduced], ['实体来源', fact.entity_refs.join('、')]],
    })),
    ...data.design_deviation_proposals.map((deviation, index) => ({
      id: `deviation:${index}`, title: `设计偏差 ${index + 1}`,
      details: [['设计来源', deviation.target_artifact_ref], ['当前设计', deviation.current_design],
        ['建议变更', deviation.proposed_change], ['理由', deviation.reason], ['后续影响', deviation.downstream_impact.join('；')]],
    })),
    ...data.continuity_questions.map((question, index) => ({
      id: `question:${index}`, title: `连续性问题 ${index + 1}`, details: [['待核对内容', question]],
    })),
    ...data.scene_contract_coverage.missing_elements.map((element, index) => ({
      id: `missing:${index}`, title: `计划缺项 ${index + 1}`, details: [['未覆盖内容', element]],
    })),
  ]
})
const pending = computed(() => items.value.filter(item => !decisions.value[item.id] || decisions.value[item.id] === 'pending').length)
const questions = computed(() => items.value.filter(item => decisions.value[item.id] === 'question').length)
watch(scope, () => {
  const cached = loadDraft<Record<string, Decision>>(scope.value)?.value
  decisions.value = Object.fromEntries(Object.entries(cached ?? {}).filter(([, status]) => ['pending', 'reviewed', 'question'].includes(status)))
  saveFailed.value = false
}, { immediate: true })

function decide(id: string, event: Event) {
  const status = (event.target as HTMLSelectElement).value as Decision
  decisions.value = { ...decisions.value, [id]: status }
  saveFailed.value = !saveDraft(scope.value, decisions.value)
}
</script>

<template>
  <section class="generation-review" aria-label="生成审核材料">
    <h5>生成审核材料 · AI 原始建议</h5>
    <p v-if="!material" class="muted">此草稿没有结构化审核材料（旧格式或本地草稿），请结合正文和生成依据人工核对。</p>
    <template v-else>
      <p class="muted">以下内容来自生成时的模型响应，作者修改正文后仍保留原建议。核对标记保存在本机，刷新后可继续。</p>
      <p role="status">{{ pending }} 项待处理 · {{ items.length - pending - questions }} 项已核对 · {{ questions }} 项保留疑问</p>
      <p v-if="saveFailed" class="error" role="alert">核对标记未能保存到本机，请重试选择。</p>
      <p class="muted">这些建议供作者判断；标记不会应用事实或规划变更。需要回写时先建立可审核提案。正文接受仍需通过严重一致性问题检查。</p>
      <dl class="review-coverage">
        <dt>目标覆盖</dt><dd>{{ material.scene_contract_coverage.goal }}</dd>
        <dt>冲突覆盖</dt><dd>{{ material.scene_contract_coverage.conflict }}</dd>
        <dt>转折覆盖</dt><dd>{{ material.scene_contract_coverage.turning_point }}</dd>
        <dt>结果覆盖</dt><dd>{{ material.scene_contract_coverage.outcome }}</dd>
        <dt>观察到的进入状态</dt><dd>{{ material.entry_state_observed.join('；') || '未提供' }}</dd>
        <dt>产生的退出状态</dt><dd>{{ material.exit_state_produced.join('；') || '未提供' }}</dd>
      </dl>
      <article v-for="item in items" :key="item.id" class="review-material-item">
        <h6>{{ item.title }}</h6>
        <dl><template v-for="[label, value] in item.details" :key="label"><dt>{{ label }}</dt><dd>{{ value || '未提供' }}</dd></template></dl>
        <label>{{ item.title }}处理状态
          <select :aria-label="`${item.title}处理状态`" :value="decisions[item.id] || 'pending'" @change="decide(item.id, $event)">
            <option value="pending">待处理</option>
            <option value="reviewed">已核对</option>
            <option value="question">保留疑问</option>
          </select>
        </label>
      </article>
      <details><summary>材料来源</summary>
        <p>{{ proposal.generation_review?.provider }} · {{ proposal.generation_review?.model }}</p>
        <p>生成记录：{{ proposal.generation_review?.generation_run_id || '未提供' }}</p>
        <ul><li v-for="source in material.source_refs" :key="source">{{ source }}</li></ul>
      </details>
    </template>
  </section>
</template>

<style scoped>
.generation-review { margin-block: 1rem; }
.generation-review h5, .generation-review h6 { font-size: 1rem; margin-block: .75rem; }
.generation-review dl { display: grid; grid-template-columns: minmax(6rem, 1fr) 4fr; gap: .5rem 1rem; }
.generation-review dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.generation-review dt { opacity: .7; }
.review-material-item { border-top: 1px solid var(--border-color, #8885); padding-block: .75rem; }
.review-material-item label { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
@media (max-width: 640px) { .generation-review dl { grid-template-columns: 1fr; } }
</style>
