import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import type { GraphAnalysisResponse } from '../types'
import { useWorkspaceStore } from './workspace'
import type { WorkspaceShell } from './workspaceShell'

/** Graph / structure analysis for the active project. */
export const useGraphStore = defineStore('graph', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }

  const graphAnalysis = ref<GraphAnalysisResponse | null>(null)
  const isLoadingGraph = ref(false)
  const graphError = ref('')

  function isActiveProject(projectId: string) {
    return projectId === ws().activeProjectId
  }

  async function loadGraphAnalysis(
    projectId = ws().activeProject?.id,
    signal?: AbortSignal,
  ) {
    graphError.value = ''
    if (!projectId) {
      graphAnalysis.value = null
      return
    }

    isLoadingGraph.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/graph/analysis`, { signal })
      if (!response.ok) {
        throw new Error('Could not load graph analysis')
      }
      const analysis = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      graphAnalysis.value = analysis
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      graphError.value = 'Graph analysis could not be loaded.'
    } finally {
      if (!signal?.aborted) {
        isLoadingGraph.value = false
      }
    }
  }

  /** Drop project-scoped state before the workspace loads another project. */
  function resetProjectState() {
    graphAnalysis.value = null
    graphError.value = ''
  }

  return {
    graphAnalysis,
    isLoadingGraph,
    graphError,
    loadGraphAnalysis,
    resetProjectState,
  }
})
