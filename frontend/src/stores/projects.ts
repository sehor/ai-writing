import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import type { ProjectSummary } from '../types'
import { useProjectContextStore } from './projectContext'

/** Project list and create form; the leaf context owns selection. */
export const useProjectsStore = defineStore('projects', () => {
  const context = useProjectContextStore()

  const projects = ref<ProjectSummary[]>([])
  const activeProject = computed(() => projects.value.find(project => project.id === context.activeProjectId))
  const newProject = ref({
    title: '',
    premise: '',
  })
  const isCreating = ref(false)
  const createError = ref('')
  const createStatus = ref('')

  async function createProject(): Promise<ProjectSummary | null> {
    createError.value = ''
    createStatus.value = ''
    const title = newProject.value.title.trim()
    const premise = newProject.value.premise.trim()
    if (!title || !premise) {
      createError.value = '请填写项目标题和故事梗概。'
      return null
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
      context.activeProjectId = created.id
      newProject.value = { title: '', premise: '' }
      createStatus.value = `Project "${created.title}" created successfully.`
      return created as ProjectSummary
    } catch {
      createError.value = '项目创建失败，请检查本地服务后重试。'
      return null
    } finally {
      isCreating.value = false
    }
  }

  /** Optimistically bump the project's current_step after a saved step. */
  function advanceActiveProject(completedStep: number) {
    const project = activeProject.value
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
    activeProject,
    projects,
    newProject,
    isCreating,
    createError,
    createStatus,
    createProject,
    advanceActiveProject,
  }
})
