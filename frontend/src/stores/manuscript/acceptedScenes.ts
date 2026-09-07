import { computed, ref } from 'vue'
import type { ManuscriptScene } from '../../types'
import type { ManuscriptFeedback } from './feedback'
import { useProjectContextStore } from '../projectContext'
import { fetchApi } from '../../api/client'

export function useAcceptedScenes(feedback: ManuscriptFeedback) {
  const context = useProjectContextStore()
  const isActiveProject = (projectId: string) => projectId === context.activeProjectId
  const { manuscriptError } = feedback
  const manuscriptScenes = ref<ManuscriptScene[]>([])
  const acceptedSceneCount = computed(() => manuscriptScenes.value.length)
  async function loadManuscriptScenes(projectId = context.activeProjectId) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptScenes.value = []
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/scenes`)
      if (!response.ok) {
        throw new Error('Could not load manuscript scenes')
      }
      const scenes = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptScenes.value = scenes
    } catch {
      manuscriptError.value = 'Accepted manuscript scenes could not be loaded.'
    }
  }

  function resetAcceptedScenes() { manuscriptScenes.value = [] }

  return {
    manuscriptScenes,
    acceptedSceneCount,
    loadManuscriptScenes,
    resetAcceptedScenes,
  }
}
