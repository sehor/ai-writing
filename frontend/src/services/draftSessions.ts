import { clearDraft, loadDraft, saveDraft, type CachedDraft } from './draftCache'
import { useEditorSessionStore } from '../stores/editorSession'

// Baselines and autosave timers live at module scope: the draft-safety net is
// app-wide by definition (one editor per scope key), matching the previous
// single workspace-store closure. Scope keys are domain-prefixed and unique.
const draftBaselines = new Map<string, string>()
const autosaveTimers = new Map<string, ReturnType<typeof setTimeout>>()

function stableValue(value: unknown): string {
  return JSON.stringify(value)
}

export function setBaseline(scopeKey: string, value: unknown): void {
  const pending = autosaveTimers.get(scopeKey)
  if (pending) clearTimeout(pending)
  autosaveTimers.delete(scopeKey)
  draftBaselines.set(scopeKey, stableValue(value))
  useEditorSessionStore().markClean(scopeKey)
}

export function isScopeDirty(scopeKey: string, value: unknown): boolean {
  return (
    draftBaselines.has(scopeKey) && draftBaselines.get(scopeKey) !== stableValue(value)
  )
}

function scopeHasProject(scopeKey: string): boolean {
  return Boolean(scopeKey.split(':')[1])
}

export function persistDraft(scopeKey: string, value: unknown): void {
  if (!scopeHasProject(scopeKey)) {
    return
  }
  const cached = saveDraft(scopeKey, value)
  if (cached) {
    useEditorSessionStore().markDirty(scopeKey, cached.savedAt)
  } else {
    useEditorSessionStore().markAutosaveFailed(scopeKey)
  }
}

export function restoreCachedDraft<T>(scopeKey: string): CachedDraft<T> | null {
  if (!scopeHasProject(scopeKey)) {
    return null
  }
  return loadDraft<T>(scopeKey)
}

export function discardSavedScope(scopeKey: string, value: unknown): void {
  clearDraft(scopeKey)
  if (scopeHasProject(scopeKey)) {
    setBaseline(scopeKey, value)
  }
}

export function formatSavedAt(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString()
}

export function queueAutosave(scopeKey: string, read: () => unknown): void {
  const existing = autosaveTimers.get(scopeKey)
  if (existing) {
    clearTimeout(existing)
  }
  autosaveTimers.set(
    scopeKey,
    setTimeout(() => {
      autosaveTimers.delete(scopeKey)
      const value = read()
      if (isScopeDirty(scopeKey, value)) {
        persistDraft(scopeKey, value)
      }
    }, 400)
  )
}

/** Re-baseline an editor after a reset and reapply any cached draft. */
export function restoreEntryDraft<T>(
  scopeKey: string,
  baselineValue: unknown,
  apply: (cached: T) => void,
  notify: (message: string) => void
): void {
  setBaseline(scopeKey, baselineValue)
  const cached = restoreCachedDraft<T>(scopeKey)
  if (cached && cached.value !== null && typeof cached.value === 'object') {
    apply(cached.value)
    useEditorSessionStore().markDirty(scopeKey, cached.savedAt)
    notify(`已恢复本地草稿（自动保存于 ${formatSavedAt(cached.savedAt)}）`)
  }
}
