<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from './stores/workspace'
import { useAnalysisJobsStore } from './stores/analysisJobs'
import { useProjectsStore } from './stores/projects'

import AppSidebar from './components/AppSidebar.vue'
import ProjectDialog from './components/ProjectDialog.vue'
import SnowflakeWorkspace from './components/SnowflakeWorkspace.vue'
import CanonWorkspace from './components/CanonWorkspace.vue'
import MemoryWorkspace from './components/MemoryWorkspace.vue'
import GraphWorkspace from './components/GraphWorkspace.vue'
import ManuscriptWorkspace from './components/ManuscriptWorkspace.vue'

const workspace = useWorkspaceStore()
const { activeSection, activeProject, apiStatus, workflowRuntime, runtimeLabel, runtimeTitle, isLoadingProject } = storeToRefs(workspace)
const { createStatus } = storeToRefs(useProjectsStore())
const { loadInitialData } = workspace

onMounted(() => {
  loadInitialData()
})
onBeforeUnmount(() => useAnalysisJobsStore().stop())
</script>

<template>
  <main class="shell">
    <AppSidebar />

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Project</p>
          <h2>{{ activeProject?.title ?? 'No Project' }}</h2>
          <p class="premise">{{ activeProject?.premise ?? 'Create a project to begin.' }}</p>
          <p v-if="createStatus" class="topbar-notice" role="status">{{ createStatus }}</p>
        </div>
        <div class="status-stack">
          <ProjectDialog />
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

      <p v-if="isLoadingProject" role="status">正在加载项目，完成后可继续编辑…</p>
      <fieldset class="workspace-content" :disabled="isLoadingProject" :aria-busy="isLoadingProject">
        <SnowflakeWorkspace v-if="activeSection === 'snowflake'" />
        <CanonWorkspace v-if="activeSection === 'canon'" />
        <MemoryWorkspace v-if="activeSection === 'memory'" />
        <GraphWorkspace v-if="activeSection === 'graph'" />
        <ManuscriptWorkspace v-if="activeSection === 'manuscript'" />
      </fieldset>
    </section>
  </main>
</template>

<style scoped>
.workspace-content { border: 0; margin: 0; padding: 0; min-width: 0; }
</style>
