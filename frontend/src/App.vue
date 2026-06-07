<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from './stores/workspace'

import Sidebar from './components/Sidebar.vue'
import SnowflakeWorkspace from './components/SnowflakeWorkspace.vue'
import CanonWorkspace from './components/CanonWorkspace.vue'
import MemoryWorkspace from './components/MemoryWorkspace.vue'
import GraphWorkspace from './components/GraphWorkspace.vue'
import ManuscriptWorkspace from './components/ManuscriptWorkspace.vue'

const store = useWorkspaceStore()
const { activeSection, activeProject, apiStatus, workflowRuntime, runtimeLabel, runtimeTitle } = storeToRefs(store)
const { loadInitialData } = store

onMounted(() => {
  loadInitialData()
})
</script>

<template>
  <main class="shell">
    <Sidebar />

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Project</p>
          <h2>{{ activeProject?.title ?? 'No Project' }}</h2>
          <p class="premise">{{ activeProject?.premise ?? 'Create a project to begin.' }}</p>
        </div>
        <div class="status-stack">
          <span class="status" :class="{ offline: apiStatus !== 'ok' }">
            API {{ apiStatus }}
          </span>
          <span
            class="status runtime"
            :class="{ local: workflowRuntime?.runtime !== 'provider_deepseek' }"
            :title="runtimeTitle"
          >
            {{ runtimeLabel }}
          </span>
        </div>
      </header>

      <SnowflakeWorkspace v-if="activeSection === 'snowflake'" />
      <CanonWorkspace v-if="activeSection === 'canon'" />
      <MemoryWorkspace v-if="activeSection === 'memory'" />
      <GraphWorkspace v-if="activeSection === 'graph'" />
      <ManuscriptWorkspace v-if="activeSection === 'manuscript'" />
    </section>
  </main>
</template>
