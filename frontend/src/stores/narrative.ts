import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import type { StoryThread, NarrativeRelation, DirectorReport } from '../types'

export const useNarrativeStore = defineStore('narrative', () => {
  const threads = ref<StoryThread[]>([])
  const relations = ref<NarrativeRelation[]>([])
  const director = ref<DirectorReport | null>(null)
  const error = ref('')
  const isLoading = ref(false)
  let controller: AbortController | undefined
  function reset() {
    controller?.abort()
    threads.value = []; relations.value = []; director.value = null
    error.value = ''; isLoading.value = false
  }
  async function load(projectId: string, sceneId = '') {
    controller?.abort()
    const request = new AbortController()
    controller = request
    isLoading.value = true
    error.value = ''
    try {
      const suffix = sceneId ? `?scene_id=${encodeURIComponent(sceneId)}` : ''
      const responses = await Promise.all([
        fetchApi(`/projects/${projectId}/story-threads`, { signal: request.signal }),
        fetchApi(`/projects/${projectId}/narrative/relations`, { signal: request.signal }),
        fetchApi(`/projects/${projectId}/narrative/director${suffix}`, { signal: request.signal }),
      ])
      if (responses.some((response) => !response.ok)) throw new Error('Narrative 状态加载失败，请刷新重试。')
      const [loadedThreads, loadedRelations, loadedDirector] = await Promise.all(responses.map((response) => response.json()))
      if (request.signal.aborted) return
      threads.value = loadedThreads; relations.value = loadedRelations; director.value = loadedDirector
    } catch (reason) {
      if (!request.signal.aborted) error.value = reason instanceof Error ? reason.message : 'Narrative 状态加载失败。'
    } finally {
      if (!request.signal.aborted) isLoading.value = false
    }
  }
  return { threads, relations, director, error, isLoading, load, reset }
})
