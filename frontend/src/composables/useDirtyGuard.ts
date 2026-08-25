import { onBeforeUnmount, onMounted } from 'vue'
import { useEditorSessionStore } from '../stores/editorSession'

let unloadGuardInstalled = false

export interface DirtyGuardOptions {
  /** Flush every dirty editor snapshot into the local draft cache. */
  flushAll: () => void
}

/**
 * Page-close protection: flush dirty editors to localStorage and let the
 * browser's native beforeunload dialog warn about unsaved work. The message
 * text of that dialog is controlled by the browser, so the in-app confirm()
 * from confirmLeave() remains the primary guard for in-app navigation.
 */
export function useDirtyGuard(options: DirtyGuardOptions) {
  const editorSession = useEditorSessionStore()

  function handleBeforeUnload(event: BeforeUnloadEvent): void {
    options.flushAll()
    if (editorSession.dirtyScopeKeys().length > 0) {
      event.preventDefault()
      event.returnValue = ''
    }
  }

  onMounted(() => {
    if (unloadGuardInstalled) {
      return
    }
    unloadGuardInstalled = true
    window.addEventListener('beforeunload', handleBeforeUnload)
  })

  onBeforeUnmount(() => {
    // The composable is mounted once from the app shell; keep the listener
    // alive for the whole session, hence no removal here.
  })

  /**
   * Ask before leaving a scope with unsaved changes. Returns true when the
   * switch may proceed; callers must abort the selection change otherwise.
   */
  function confirmLeave(scopeKey: string, label: string): boolean {
    if (!editorSession.isDirty(scopeKey)) {
      return true
    }
    return window.confirm(
      `「${label}」有未保存的修改。\n` +
        '确定离开：修改会先自动保存为本地草稿，稍后回到此页面可恢复。\n' +
        '取消：留在当前编辑器继续修改。'
    )
  }

  /**
   * Aggregate variant for switches (e.g. project switch) that may leave
   * several dirty scopes at once.
   */
  function confirmLeaveMultiple(dirtyCount: number): boolean {
    return window.confirm(
      `当前项目有 ${dirtyCount} 处未保存的修改。\n` +
        '确定离开：修改会自动保存为本地草稿，回到该项目时可恢复。\n' +
        '取消：留在当前项目。'
    )
  }

  return { confirmLeave, confirmLeaveMultiple }
}
