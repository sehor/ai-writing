<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useGraphStore } from '../stores/graph'
import NarrativePanel from './NarrativePanel.vue'
import { useManuscriptStore } from '../stores/manuscript'
import { useCanonStore } from '../stores/canon'
import { statusText } from '../utils/format'

const workspace = useWorkspaceStore()
const manuscript = useManuscriptStore()
const canon = useCanonStore()
function canLocate(id: string) {
  return (
    manuscript.sceneContracts.some((scene) => scene.id === id) ||
    canon.canonEntities.some((entity) => entity.id === id)
  )
}
function locate(id: string) {
  if (manuscript.sceneContracts.some((scene) => scene.id === id)) {
    manuscript.activeSceneId = id
    workspace.activeSection = 'manuscript'
  } else if (canon.canonEntities.some((entity) => entity.id === id)) {
    canon.activeCanonId = id
    workspace.activeSection = 'canon'
  }
}
const { activeProject } = storeToRefs(workspace)
const graph = useGraphStore()
const { isLoadingGraph, graphError, graphAnalysis } = storeToRefs(graph)
const { loadGraphAnalysis } = graph
</script>

<template>
  <section class="graph-workspace">
    <div class="panel-header">
      <div>
        <h3>叙事分析</h3>
      </div>
      <button
        class="secondary"
        type="button"
        :disabled="isLoadingGraph || !activeProject"
        @click="loadGraphAnalysis()"
      >
        {{ isLoadingGraph ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <p v-if="graphError" class="error">{{ graphError }}</p>
    <p v-else-if="!graphAnalysis" class="empty-state">
      暂无结构分析结果。加载项目后可刷新查看。
    </p>

    <template v-if="graphAnalysis">
      <div class="graph-summary" aria-label="Graph summary">
        <div>
          <span>{{ graphAnalysis.summary.node_count }}</span>
          <small>节点</small>
        </div>
        <div>
          <span>{{ graphAnalysis.summary.edge_count }}</span>
          <small>关系</small>
        </div>
        <div>
          <span>{{ graphAnalysis.summary.risk_count }}</span>
          <small>风险</small>
        </div>
        <div>
          <span>{{ graphAnalysis.summary.unresolved_thread_count }}</span>
          <small>未完结线索</small>
        </div>
        <div>
          <span>{{ graphAnalysis.summary.canon_reference_count }}</span>
          <small>设定引用</small>
        </div>
      </div>

      <section class="graph-panel">
        <div class="panel-header compact">
          <div>
            <h4>结构风险</h4>
          </div>
          <span class="step-chip">
            {{ graphAnalysis.summary.critical_count }} 严重 /
            {{ graphAnalysis.summary.warning_count }} 提醒
          </span>
        </div>
        <div class="risk-list">
          <article
            v-for="risk in graphAnalysis.risks"
            :key="risk.id"
            class="risk-item"
            :class="risk.severity"
          >
            <strong>{{ risk.title }}</strong>
            <p>{{ risk.detail }}</p>
            <small>{{ statusText(risk.severity) }}</small
            ><button
              v-if="canLocate(risk.source_id)"
              class="quiet-button"
              @click="locate(risk.source_id)"
            >
              查看相关内容
            </button>
          </article>
          <p v-if="graphAnalysis.risks.length === 0" class="empty-state">
            目前没有发现结构风险。
          </p>
        </div>
      </section>

      <details class="graph-detail-disclosure">
        <summary>节点与关系详情</summary>
        <div class="graph-tables">
          <section class="graph-panel">
            <p class="eyebrow">节点</p>
            <div class="graph-table">
              <div
                v-for="node in graphAnalysis.nodes"
                :key="node.id"
                class="graph-row"
              >
                <strong>{{ node.label }}</strong>
                <span>{{ node.node_type }}</span>
                <small>{{ node.status || node.id }}</small>
              </div>
            </div>
          </section>
          <section class="graph-panel">
            <p class="eyebrow">关系</p>
            <div class="graph-table">
              <div
                v-for="edge in graphAnalysis.edges"
                :key="`${edge.source}-${edge.edge_type}-${edge.target}-${edge.label}`"
                class="graph-row"
              >
                <strong>{{ edge.edge_type }}</strong>
                <span>{{ edge.source }} -> {{ edge.target }}</span>
                <small>{{ edge.label || 'link' }}</small>
              </div>
            </div>
          </section>
        </div>
      </details>
      <details>
        <summary>叙事状态与导演建议</summary>
        <NarrativePanel />
      </details>
    </template>
  </section>
</template>
