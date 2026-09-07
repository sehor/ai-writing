import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import type { OutboxJob, OutboxJobType } from '../types'

export function analysisJobState(job: OutboxJob): string {
  if (job.execution?.outcome === 'not_executed') return '未执行'
  if (job.execution?.outcome === 'limited') return '有限检查完成'
  return { pending: '待执行', processing: '执行中', succeeded: '已完成', failed: '失败' }[job.status]
}

const labels: Record<OutboxJobType, string> = {
  llm_wiki_ingest: 'Wiki index', consistency_analysis: 'Consistency report',
  writeback_analysis: 'Write-back suggestions', clp_extraction: 'CLP extraction',
}
export const analysisJobLabel = (type: OutboxJobType): string => labels[type] ?? `Unsupported task: ${type}`
type Settled = (jobs: OutboxJob[], signal: AbortSignal) => Promise<void>

/** Polling owns no manuscript/review state and never reads the workspace store. */
export const useAnalysisJobsStore = defineStore('analysisJobs', () => {
  const jobs = ref<OutboxJob[]>([])
  const error = ref('')
  const isLoading = ref(false)
  const retryingId = ref('')
  const limit = ref(100)
  const canLoadMore = computed(() => jobs.value.length >= limit.value && limit.value < 500)
  let projectId = ''
  let controller = new AbortController()
  let requestVersion = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let onSettled: Settled | undefined

  function stop() {
    clearTimeout(timer)
    controller.abort()
    controller = new AbortController()
    requestVersion++
    projectId = ''
    jobs.value = []
    error.value = ''
    isLoading.value = false
    retryingId.value = ''
    limit.value = 100
    onSettled = undefined
  }

  async function load(id: string, settled?: Settled) {
    if (!id) { stop(); return }
    if (projectId !== id) { stop(); projectId = id }
    if (settled) onSettled = settled
    clearTimeout(timer)
    const version = ++requestVersion
    const signal = controller.signal
    const current = () => !signal.aborted && version === requestVersion
    isLoading.value = true
    try {
      const response = await fetchApi(`/projects/${id}/outbox-jobs?aggregate_type=manuscript_revision&limit=${limit.value}`, { signal })
      if (!response.ok) throw new Error('Could not load analysis jobs')
      const loaded: OutboxJob[] = await response.json()
      if (!current()) return
      const previous = new Map(jobs.value.map((job) => [job.id, job]))
      jobs.value = loaded
      error.value = ''
      const completed = loaded.filter((job) => job.status === 'succeeded' &&
        (previous.get(job.id)?.status !== 'succeeded' || previous.get(job.id)?.attempt_count !== job.attempt_count))
      if (completed.length && onSettled) await onSettled(completed, signal)
      if (current() && loaded.some((job) => job.status === 'pending' || job.status === 'processing')) {
        timer = setTimeout(() => { void load(id) }, 800)
      }
    } catch (reason) {
      if (!current()) return
      error.value = reason instanceof Error ? reason.message : 'Could not load analysis jobs'
      // Retain the last visible state, including Retry and Refresh, on outages.
      timer = setTimeout(() => { void load(id) }, 2500)
    } finally {
      if (current()) isLoading.value = false
    }
  }

  async function retry(jobId: string) {
    if (!projectId || retryingId.value) return
    const id = projectId
    const signal = controller.signal
    retryingId.value = jobId
    error.value = ''
    try {
      const response = await fetchApi(`/projects/${id}/outbox-jobs/${jobId}/retry`, { method: 'POST', signal })
      if (!response.ok) throw new Error((await readErrorDetail(response)).message || 'Retry failed')
      const queued: OutboxJob = await response.json()
      if (signal.aborted) return
      jobs.value = jobs.value.map((job) => job.id === queued.id ? queued : job)
      await load(id)
    } catch (reason) {
      if (!signal.aborted) error.value = reason instanceof Error ? reason.message : 'Retry failed'
    } finally {
      if (!signal.aborted) retryingId.value = ''
    }
  }

  async function loadMore() {
    if (canLoadMore.value) { limit.value += 100; await load(projectId) }
  }

  return { jobs, error, isLoading, retryingId, canLoadMore, load, retry, loadMore, stop }
})
