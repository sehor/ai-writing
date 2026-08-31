<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useGraphStore } from '../stores/graph'
import NarrativePanel from './NarrativePanel.vue'

const workspace = useWorkspaceStore()
const { activeProject } = storeToRefs(workspace)
const graph = useGraphStore()
const {
  isLoadingGraph,
  graphError,
  graphAnalysis
} = storeToRefs(graph)
const {
  loadGraphAnalysis
} = graph
</script>

<template>
<section class="graph-workspace">
        <NarrativePanel />
        <div class="panel-header">
          <div>
            <p class="eyebrow">Graph / Structure</p>
            <h3>Narrative Analysis</h3>
          </div>
          <button
            class="secondary"
            type="button"
            :disabled="isLoadingGraph || !activeProject"
            @click="loadGraphAnalysis()"
          >
            {{ isLoadingGraph ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <p v-if="graphError" class="error">{{ graphError }}</p>
        <p v-else-if="!graphAnalysis" class="empty-state">
          No graph analysis loaded.
        </p>

        <template v-if="graphAnalysis">
          <div class="graph-summary" aria-label="Graph summary">
            <div>
              <span>{{ graphAnalysis.summary.node_count }}</span>
              <small>Nodes</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.edge_count }}</span>
              <small>Edges</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.risk_count }}</span>
              <small>Risks</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.unresolved_thread_count }}</span>
              <small>Open Threads</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.canon_reference_count }}</span>
              <small>Canon Refs</small>
            </div>
          </div>

          <section class="graph-panel">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">Review Queue</p>
                <h4>Structural Risks</h4>
              </div>
              <span class="step-chip">
                {{ graphAnalysis.summary.critical_count }} critical /
                {{ graphAnalysis.summary.warning_count }} warning
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
                <small>{{ risk.severity }} · {{ risk.source_id || 'project' }}</small>
              </article>
              <p v-if="graphAnalysis.risks.length === 0" class="empty-state">
                No structural risks detected.
              </p>
            </div>
          </section>

          <div class="graph-tables">
            <section class="graph-panel">
              <p class="eyebrow">Nodes</p>
              <div class="graph-table">
                <div v-for="node in graphAnalysis.nodes" :key="node.id" class="graph-row">
                  <strong>{{ node.label }}</strong>
                  <span>{{ node.node_type }}</span>
                  <small>{{ node.status || node.id }}</small>
                </div>
              </div>
            </section>
            <section class="graph-panel">
              <p class="eyebrow">Edges</p>
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
        </template>
      </section>
</template>
