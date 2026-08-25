import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import type { ProjectSummary } from '../types'
import { useWorkspaceStore } from './workspace'
import type { WorkspaceShell } from './workspaceShell'

/** Project list plus the create form; selection itself lives in the workspace store. */
export const useProjectsStore = defineStore('projects', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }

  const projects = ref<ProjectSummary[]>([])
  const newProject = ref({
    title: '',
    premise: '',
  })
  const isCreating = ref(false)
  const createError = ref('')

  async function createProject() {
    createError.value = ''
    const title = newProject.value.title.trim()
    const premise = newProject.value.premise.trim()
    if (!title || !premise) {
      createError.value = 'Title and premise are required.'
      return
    }

    isCreating.value = true
    try {
      const response = await fetchApi('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, premise }),
      })
      if (!response.ok) {
        throw new Error('Could not create project')
      }
      const created = await response.json()
      projects.value = [...projects.value, created]
      // Switching the workspace selection triggers the project load fan-out.
      ws().activeProjectId = created.id
      newProject.value = { title: '', premise: '' }
    } catch {
      createError.value = 'Project creation failed. Check that the API is running.'
    } finally {
      isCreating.value = false
    }
  }

  /** Optimistically bump the project's current_step after a saved step. */
  function advanceActiveProject(completedStep: number) {
    const project = ws().activeProject
    if (!project) {
      return
    }
    const nextStep = Math.min(completedStep + 1, 10)
    projects.value = projects.value.map((item) =>
      item.id === project.id
        ? { ...item, current_step: Math.max(item.current_step, nextStep) }
        : item
    )
  }

  return {
    projects,
    newProject,
    isCreating,
    createError,
    createProject,
    advanceActiveProject,
  }
})
