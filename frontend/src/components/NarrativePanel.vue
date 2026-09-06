<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useNarrativeStore } from '../stores/narrative'
import { useWorkspaceStore } from '../stores/workspace'
import { useManuscriptStore } from '../stores/manuscript'
const narrative = useNarrativeStore()
const workspace = useWorkspaceStore()
const manuscript = useManuscriptStore()
const { threads, relations, director, error, isLoading } = storeToRefs(narrative)
</script>

<template>
  <section class="narrative-panel">
    <div class="panel-header">
      <div><h3>故事线与已确认关系</h3></div>
      <button type="button" class="secondary" :disabled="isLoading || !workspace.activeProjectId"
        @click="narrative.load(workspace.activeProjectId, manuscript.activeSceneId)">刷新叙事状态</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!threads.length && !relations.length" class="empty-state">尚无故事线或已确认关系。CLP 提案经人工接受后会出现在这里。</p>
    <div v-if="threads.length" class="narrative-threads">
      <article v-for="thread in threads" :key="thread.id" :data-thread-id="thread.id">
        <strong>{{ thread.title }}</strong> <span class="step-chip">{{ thread.status }}</span>
        <p>{{ thread.thread_type }} · 重要度 {{ thread.importance }} · 预计回收 {{ thread.target_payoff_from ?? '未设定' }}–{{ thread.target_payoff_to ?? '未设定' }}</p>
      </article>
    </div>
    <table v-if="relations.length" class="writeback-changes">
      <thead><tr><th>来源</th><th>关系</th><th>目标</th><th>有效场景</th><th>置信度</th></tr></thead>
      <tbody><tr v-for="relation in relations" :key="relation.id">
        <td>{{ relation.source }}</td><td>{{ relation.relation }}</td><td>{{ relation.target }}</td>
        <td>{{ relation.valid_from }}–{{ relation.valid_to ?? '持续' }}</td><td>{{ relation.confidence }}</td>
      </tr></tbody>
    </table>
    <section v-if="director" class="director-report">
      <h4>Director · 场景 {{ director.scene_sequence }}</h4>
      <p class="empty-state">以下仅为结构建议，不会自动修改故事状态。</p>
      <p v-if="!director.findings.length">当前场景没有结构提示。</p>
      <article v-for="(finding, index) in director.findings" :key="`${finding.code}-${index}`">
        <strong>{{ finding.title }}</strong> <span class="severity-chip">{{ finding.severity }}</span><p>{{ finding.detail }}</p>
      </article>
    </section>
  </section>
</template>
