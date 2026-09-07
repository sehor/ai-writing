<script setup lang="ts">
import type { SceneProposal } from '../../types'
defineProps<{ proposal: SceneProposal }>()
const labels: Record<string, string> = {
  sequence: '场景序号', title: '标题', chapter_id: '章节', pov: '叙述视角', goal: '目标', conflict: '冲突',
  turning_point: '转折', outcome: '结果', required_canon: '必要设定', forbidden_facts: '禁止事实',
  information_delta: '信息变化', character_state_delta: '角色状态变化', story_thread_actions: '故事线动作',
  open_threads: '旧版线索', source_artifact_step: '来源步骤',
}
</script>

<template>
  <details v-if="proposal.operation === 'update'" class="scene-update-review">
    <summary>更新原场景 · 核对差异</summary>
    <p>来自记录 {{ proposal.source_record_id }} · 规划版本 {{ proposal.expected_plan_version }}</p>
    <p>接受后保留场景和正文历史；若目标已修改，请重新编译并核对最新差异。</p>
    <dl>
      <template v-for="(change, field) in proposal.changes" :key="field">
        <dt>{{ labels[field] || field }}</dt>
        <dd><span>当前：{{ change.before || '（空）' }}</span><br><span>建议：{{ change.after || '（空）' }}</span></dd>
      </template>
    </dl>
    <p v-if="!Object.keys(proposal.changes || {}).length">场景字段未变化，仅更新来源版本。</p>
  </details>
</template>

<style scoped>
.scene-update-review { min-width: 14rem; max-width: 28rem; }
dd { margin-left: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
dt { margin-top: .5rem; font-weight: 600; }
</style>
