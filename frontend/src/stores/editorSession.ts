import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface EditorDraftState {
  scopeKey: string
  dirty: boolean
  lastSavedAt?: string
  lastAutosavedAt?: string
  autosaveFailed?: boolean
}

/**
 * Registry of open editors and their draft state. The workspace store owns
 * draft VALUES; this store only tracks WHERE unsaved work lives so guards,
 * status labels, and unload handlers can reason about it.
 */
export const useEditorSessionStore = defineStore('editorSession', () => {
  const editors = ref<Record<string, EditorDraftState>>({})

  function registerEditor(scopeKey: string): void {
    if (!editors.value[scopeKey]) {
      editors.value[scopeKey] = { scopeKey, dirty: false }
    }
  }

  function markDirty(scopeKey: string, autosavedAt?: string): void {
    const current = editors.value[scopeKey]
    editors.value[scopeKey] = {
      scopeKey,
      dirty: true,
      lastSavedAt: current?.lastSavedAt,
      lastAutosavedAt: autosavedAt,
      autosaveFailed: false,
    }
  }

  function markClean(scopeKey: string, savedAt?: string): void {
    const current = editors.value[scopeKey]
    editors.value[scopeKey] = {
      scopeKey,
      dirty: false,
      lastSavedAt: savedAt ?? current?.lastSavedAt,
      lastAutosavedAt: undefined,
    }
  }

  function dropEditor(scopeKey: string): void {
    delete editors.value[scopeKey]
  }

  function markAutosaveFailed(scopeKey: string) {
    markDirty(scopeKey)
    editors.value[scopeKey]!.autosaveFailed = true
  }

  function draftState(scopeKey: string): EditorDraftState | null {
    return editors.value[scopeKey] ?? null
  }

  function isDirty(scopeKey: string): boolean {
    return editors.value[scopeKey]?.dirty === true
  }

  function dirtyScopeKeys(): string[] {
    return Object.values(editors.value)
      .filter((state) => state.dirty)
      .map((state) => state.scopeKey)
  }

  return {
    editors,
    registerEditor,
    markDirty,
    markClean,
    markAutosaveFailed,
    dropEditor,
    draftState,
    isDirty,
    dirtyScopeKeys,
  }
})
