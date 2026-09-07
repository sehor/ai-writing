import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { ModelExecutionOptions } from '../types'

/** Leaf selection state: usable without loading the workspace or any domain. */
export const useProjectContextStore = defineStore('projectContext', () => {
  const activeProjectId = ref('')
  const activeStepNumber = ref(1)
  const projectReload = ref(0)
  const selectedModelProfile = ref(localStorage.getItem('ai-writing:model-profile') ?? '')

  watch(selectedModelProfile, (profileId) => {
    localStorage.setItem('ai-writing:model-profile', profileId)
  })

  function modelExecutionOptions(): ModelExecutionOptions {
    return { model_profile: selectedModelProfile.value, allow_fallback: true, allow_repair: true }
  }

  function reloadActiveProject() { projectReload.value += 1 }

  return { activeProjectId, activeStepNumber, projectReload, selectedModelProfile, modelExecutionOptions, reloadActiveProject }
})
