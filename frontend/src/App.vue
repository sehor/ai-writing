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
const { activeSection, activeProject, apiStatus, workflowRuntime, runtimeLabel, runtimeTitle, isLoadingProject, modelProfiles, selectedModelProfile } = storeToRefs(workspace)
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
          <label class="model-picker">
            <span>Model</span>
            <select v-model="selectedModelProfile" aria-label="Generation model">
              <option value="">Auto / local fallback</option>
              <option v-for="profile in modelProfiles" :key="profile.id" :value="profile.id">
                {{ profile.label }}{{ profile.configured ? '' : ' (not configured)' }}
              </option>
            </select>
          </label>
          <span class="status" :class="{ offline: apiStatus !== 'ok' }">
            API {{ apiStatus }}
          </span>
          <span
            class="status runtime"
            :class="{ local: workflowRuntime?.runtime_kind === 'local_deterministic' || !workflowRuntime?.provider_configured }"
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
.model-picker { display: flex; align-items: center; gap: .45rem; font-size: .75rem; color: var(--muted); }
.model-picker select { max-width: 18rem; padding: .38rem .55rem; border: 1px solid var(--line); border-radius: .45rem; background: var(--panel); color: var(--text); }
</style>
