<script setup lang="ts">
import type { OutboxJob } from '../../types'
defineProps<{ job: OutboxJob }>()
const modes = { local_rules: '本地文本规则', local_cognition: '本地回写候选', index: 'Wiki 索引',
  external_clp: '外部 CLP 抽取', not_configured: '未配置', unavailable: '配置不可用' }
const outcomes = { completed: '已执行', limited: '有限检查 · 未执行模型审稿', not_executed: '未执行', failed: '失败' }
</script>

<template>
  <div class="analysis-execution" aria-label="分析执行范围">
    <template v-if="job.execution">
      <p><strong>{{ modes[job.execution.mode] }} · {{ outcomes[job.execution.outcome] }}</strong></p>
      <p>{{ job.execution.limitations }}</p>
      <small>处理器：{{ job.execution.processor }} · 来源：{{ job.execution.source_ref }}</small>
    </template>
    <p v-else>{{ job.status === 'pending' || job.status === 'processing' ? '任务尚未完成，执行范围待记录。' : '旧任务执行范围未知，不据此宣称模型检查已完成。' }}</p>
  </div>
</template>
