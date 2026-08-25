import type { WorkflowAgentTrace } from '../types'

/** Normalized failure for non-2xx API responses raised by the typed client. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface ApiErrorDetail {
  message?: string
  workflow_trace?: WorkflowAgentTrace[]
}

/**
 * Extract a human-readable message (and optional workflow trace) from a
 * FastAPI-style error body. Never throws: unreadable bodies degrade to an
 * empty detail object so callers keep their own fallback copy.
 */
export async function readErrorDetail(response: Response): Promise<ApiErrorDetail> {
  try {
    const payload = await response.json()
    if (typeof payload.detail === 'string') {
      return { message: payload.detail }
    }
    return payload.detail ?? {}
  } catch {
    return {}
  }
}
