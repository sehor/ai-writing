const STORAGE_PREFIX = 'ai-writing:draft:v1:'

export interface CachedDraft<T> {
  savedAt: string
  value: T
}

function storageKey(scopeKey: string): string {
  return `${STORAGE_PREFIX}${scopeKey}`
}

/**
 * Persist an editor snapshot for a scope key. Returns the stored envelope so
 * callers can surface the autosave time; failures (quota, private mode) are
 * swallowed because losing a safety net must never break editing itself.
 */
export function saveDraft<T>(scopeKey: string, value: T): CachedDraft<T> | null {
  try {
    const cached: CachedDraft<T> = { savedAt: new Date().toISOString(), value }
    window.localStorage.setItem(storageKey(scopeKey), JSON.stringify(cached))
    return cached
  } catch {
    return null
  }
}

export function loadDraft<T>(scopeKey: string): CachedDraft<T> | null {
  try {
    const raw = window.localStorage.getItem(storageKey(scopeKey))
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as CachedDraft<T>
    if (!parsed || typeof parsed.savedAt !== 'string') {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function clearDraft(scopeKey: string): void {
  try {
    window.localStorage.removeItem(storageKey(scopeKey))
  } catch {
    // Nothing to do; the cache is best effort.
  }
}
