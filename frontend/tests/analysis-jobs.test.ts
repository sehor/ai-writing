import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAnalysisJobsStore } from '../src/stores/analysisJobs'
import { fetchApi } from '../src/api/client'
import type { OutboxJob } from '../src/types'

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
const job = (status: OutboxJob['status'], project = 'a'): OutboxJob => ({
  id: `${project}-job`, project_id: project, job_type: 'clp_extraction', aggregate_type: 'manuscript_revision',
  aggregate_id: 'revision', payload: {}, status, attempt_count: 1, last_error: '', created_at: '', completed_at: '', processing_started_at: '',
})
beforeEach(() => { setActivePinia(createPinia()); vi.useFakeTimers(); vi.mocked(fetchApi).mockReset() })
afterEach(() => { useAnalysisJobsStore().stop(); vi.useRealTimers() })

test('CLP transitions automatically to terminal state and polling stops', async () => {
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json([job('pending')]))
    .mockResolvedValueOnce(Response.json([job('processing')]))
    .mockResolvedValueOnce(Response.json([job('succeeded')]))
  const completed = vi.fn().mockResolvedValue(undefined)
  const jobs = useAnalysisJobsStore()
  await jobs.load('a', completed)
  expect(jobs.jobs[0].job_type).toBe('clp_extraction')
  await vi.advanceTimersByTimeAsync(800)
  expect(jobs.jobs[0].status).toBe('processing')
  await vi.advanceTimersByTimeAsync(800)
  expect(jobs.jobs[0].status).toBe('succeeded')
  expect(completed).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(10_000)
  expect(fetchApi).toHaveBeenCalledTimes(3)
})

test('switching projects aborts old requests, even on A to B to A', async () => {
  let resolveOld!: (response: Response) => void
  vi.mocked(fetchApi).mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
    .mockResolvedValueOnce(Response.json([job('failed', 'b')]))
    .mockResolvedValueOnce(Response.json([job('succeeded', 'a')]))
  const jobs = useAnalysisJobsStore()
  const stale = jobs.load('a')
  const signal = vi.mocked(fetchApi).mock.calls[0][1]?.signal
  await jobs.load('b')
  await jobs.load('a')
  resolveOld(Response.json([job('pending', 'a')]))
  await stale
  expect(signal?.aborted).toBe(true)
  expect(jobs.jobs[0].status).toBe('succeeded')
  await vi.advanceTimersByTimeAsync(4000)
  expect(fetchApi).toHaveBeenCalledTimes(3)
})

test('a reopened project recovers failed jobs and async retry resumes polling', async () => {
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json([job('failed')]))
    .mockResolvedValueOnce(Response.json(job('pending'), { status: 202 }))
    .mockResolvedValueOnce(Response.json([job('pending')]))
    .mockResolvedValueOnce(Response.json([job('succeeded')]))
  const jobs = useAnalysisJobsStore()
  await jobs.load('a')
  expect(jobs.jobs[0].status).toBe('failed')
  await jobs.retry('a-job')
  expect(fetchApi).toHaveBeenCalledWith('/projects/a/outbox-jobs/a-job/retry', expect.objectContaining({ method: 'POST' }))
  await vi.advanceTimersByTimeAsync(800)
  expect(jobs.jobs[0].status).toBe('succeeded')
})

test('refresh errors retain failed jobs and stop cancels retry timers', async () => {
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json([job('failed')])).mockRejectedValueOnce(new Error('offline'))
  const jobs = useAnalysisJobsStore()
  await jobs.load('a'); await jobs.load('a')
  expect(jobs.error).toBe('offline')
  expect(jobs.jobs[0].status).toBe('failed')
  jobs.stop()
  await vi.advanceTimersByTimeAsync(5000)
  expect(fetchApi).toHaveBeenCalledTimes(2)
})
