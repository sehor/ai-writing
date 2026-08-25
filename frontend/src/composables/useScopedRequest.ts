export interface RequestScope {
  projectId: string
  domain: string
  entityId: string
  requestId: number
}

const counters = new Map<string, number>()
const latest = new Map<string, number>()

function slotOf(scope: Pick<RequestScope, 'projectId' | 'domain' | 'entityId'>): string {
  return `${scope.projectId}|${scope.domain}|${scope.entityId}`
}

/**
 * Async response isolation. Begin a scope right before an async request and
 * validate with isCurrent() after it resolves but BEFORE writing any shared
 * state. A scope stops being current when a newer request targets the same
 * project+domain+entity slot — e.g. the user re-generated, switched Snowflake
 * steps, or switched projects and came back.
 */
export function useScopedRequest() {
  function begin(projectId: string, domain: string, entityId: string): RequestScope {
    const slot = slotOf({ projectId, domain, entityId })
    const next = (counters.get(slot) ?? 0) + 1
    counters.set(slot, next)
    latest.set(slot, next)
    return { projectId, domain, entityId, requestId: next }
  }

  function isCurrent(scope: RequestScope): boolean {
    return latest.get(slotOf(scope)) === scope.requestId
  }

  return { begin, isCurrent }
}
