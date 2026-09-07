import { computed, ref, watch, type Ref } from 'vue'
import { useEditorSessionStore } from '../editorSession'
import { confirmLeave } from '../../composables/useDirtyGuard'
import { clearDraft } from '../../services/draftCache'
import { formatSavedAt, isScopeDirty, persistDraft, queueAutosave, restoreCachedDraft, setBaseline } from '../../services/draftSessions'
import type { ManuscriptScene } from '../../types'
import type { ManuscriptFeedback } from './feedback'
import { useProjectContextStore } from '../projectContext'
import { fetchApi } from '../../api/client'

type ManuscriptEditDraft = { title: string; content: string; expected_scene_version: number | null }

interface EditingDependencies {
  manuscriptScenes: Ref<ManuscriptScene[]>
  refreshCommittedRevision: (projectId: string) => Promise<void>
  invalidateHistoryOutput: () => void
}

export function useManuscriptEditing(feedback: ManuscriptFeedback, { manuscriptScenes, refreshCommittedRevision, invalidateHistoryOutput }: EditingDependencies) {
  const context = useProjectContextStore()
  const isActiveProject = (projectId: string) => projectId === context.activeProjectId
  const { manuscriptError, manuscriptStatus } = feedback
  const editorSession = useEditorSessionStore()
  const isSavingManuscriptScene = ref(false)
  const editingManuscriptSceneId = ref('')
  const manuscriptEditTitle = ref('')
  const manuscriptEditContent = ref('')
  const manuscriptEditVersion = ref<number | null>(null)
  const manuscriptSaveConflict = ref(false)
  const manuscriptEditReviewReady = ref(false)
  const isRefreshingManuscriptEdit = ref(false)
  let manuscriptEditProjectId = ''
  let manuscriptEditSession = 0
  let hydratingManuscriptEdit = false
  const editingManuscriptScene = computed(() =>
    manuscriptScenes.value.find((scene) => scene.scene_id === editingManuscriptSceneId.value)
  )
  const manuscriptEditNeedsReview = computed(() =>
    !!editingManuscriptSceneId.value && (manuscriptSaveConflict.value ||
      manuscriptEditVersion.value === null ||
      manuscriptEditVersion.value !== editingManuscriptScene.value?.version)
  )
  function manuscriptEditScopeKey(
    projectId = context.activeProjectId,
    sceneId = editingManuscriptSceneId.value
  ): string {
    return `manuscript:${projectId}:${sceneId || 'new'}`
  }

  function currentManuscriptEdits(): ManuscriptEditDraft {
    return {
      title: manuscriptEditTitle.value,
      content: manuscriptEditContent.value,
      expected_scene_version: manuscriptEditVersion.value,
    }
  }
  watch(
    [manuscriptEditTitle, manuscriptEditContent, manuscriptEditVersion],
    () => {
      if (hydratingManuscriptEdit || !editingManuscriptSceneId.value) return
      const key = manuscriptEditScopeKey(manuscriptEditProjectId)
      const snapshot = currentManuscriptEdits()
      if (isScopeDirty(key, snapshot)) editorSession.markDirty(key)
      else editorSession.markClean(key)
      // A delayed autosave must not read a different scene or project.
      queueAutosave(key, () => snapshot)
    },
    { flush: 'sync' }
  )
  function startEditingManuscriptScene(scene: ManuscriptScene) {
    if (isSavingManuscriptScene.value) return
    const currentScope = manuscriptEditScopeKey(manuscriptEditProjectId)
    if (
      editingManuscriptSceneId.value &&
      isScopeDirty(currentScope, currentManuscriptEdits())
    ) {
      if (!confirmLeave(currentScope, `场景 ${editingManuscriptSceneId.value} 的正文编辑`)) {
        return
      }
      persistDraft(currentScope, currentManuscriptEdits())
    }
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    hydratingManuscriptEdit = true
    manuscriptEditSession++
    manuscriptEditProjectId = context.activeProjectId
    manuscriptSaveConflict.value = false
    manuscriptEditReviewReady.value = true
    isRefreshingManuscriptEdit.value = false
    editingManuscriptSceneId.value = scene.scene_id
    const nextScope = manuscriptEditScopeKey(context.activeProjectId, scene.scene_id)
    const baseline = { title: scene.title, content: scene.content, expected_scene_version: scene.version }
    setBaseline(nextScope, baseline)
    const cached = restoreCachedDraft<ManuscriptEditDraft>(nextScope)
    if (cached && typeof cached.value?.title === 'string' && typeof cached.value.content === 'string') {
      manuscriptEditTitle.value = cached.value.title
      manuscriptEditContent.value = cached.value.content
      const version = cached.value.expected_scene_version
      manuscriptEditVersion.value = typeof version === 'number' && Number.isInteger(version) && version >= 1 ? version : null
      editorSession.markDirty(nextScope, cached.savedAt)
      manuscriptStatus.value = `已恢复本地草稿（自动保存于 ${formatSavedAt(cached.savedAt)}）`
    } else {
      manuscriptEditTitle.value = scene.title
      manuscriptEditContent.value = scene.content
      manuscriptEditVersion.value = scene.version
    }
    hydratingManuscriptEdit = false
  }

  function cancelEditingManuscriptScene() {
    const key = manuscriptEditScopeKey(manuscriptEditProjectId)
    if (editingManuscriptSceneId.value && isScopeDirty(key, currentManuscriptEdits())) {
      persistDraft(key, currentManuscriptEdits())
    }
    hydratingManuscriptEdit = true
    manuscriptEditSession++
    editingManuscriptSceneId.value = ''
    manuscriptEditTitle.value = ''
    manuscriptEditContent.value = ''
    manuscriptEditVersion.value = null
    manuscriptEditProjectId = ''
    manuscriptSaveConflict.value = false
    manuscriptEditReviewReady.value = false
    isRefreshingManuscriptEdit.value = false
    isSavingManuscriptScene.value = false
    hydratingManuscriptEdit = false
  }

  async function refreshManuscriptEditConflict() {
    if (!editingManuscriptSceneId.value || isRefreshingManuscriptEdit.value) return
    const projectId = manuscriptEditProjectId
    const session = manuscriptEditSession
    manuscriptEditReviewReady.value = false
    isRefreshingManuscriptEdit.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/scenes`)
      if (!response.ok) throw new Error('Could not load current text')
      const scenes: ManuscriptScene[] = await response.json()
      if (session !== manuscriptEditSession || !isActiveProject(projectId)) return
      manuscriptScenes.value = scenes
      manuscriptEditReviewReady.value = !!editingManuscriptScene.value
      manuscriptError.value = editingManuscriptScene.value
        ? '正文版本已变更。你的编辑已保留，请核对当前正文后再保存。'
        : '当前正文已不存在。你的编辑已保留，请先检查项目状态。'
    } catch {
      if (session === manuscriptEditSession && isActiveProject(projectId)) {
        manuscriptError.value = '读取当前正文失败。你的编辑已保留，请重试读取后再确认版本。'
      }
    } finally {
      if (session === manuscriptEditSession) isRefreshingManuscriptEdit.value = false
    }
  }

  function rebaseManuscriptSceneEdit() {
    if (!manuscriptEditReviewReady.value || isRefreshingManuscriptEdit.value ||
        isSavingManuscriptScene.value || !editingManuscriptScene.value) return
    manuscriptEditVersion.value = editingManuscriptScene.value.version
    manuscriptSaveConflict.value = false
    persistDraft(manuscriptEditScopeKey(manuscriptEditProjectId), currentManuscriptEdits())
    manuscriptError.value = ''
    manuscriptStatus.value = `已确认当前 v${manuscriptEditVersion.value}；编辑内容保留，尚未保存。`
  }

  async function saveManuscriptSceneEdit(sceneId: string) {
    if (isSavingManuscriptScene.value || sceneId !== editingManuscriptSceneId.value) return
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = context.activeProjectId
    const title = manuscriptEditTitle.value.trim()
    const content = manuscriptEditContent.value.trim()

    if (!projectId) {
      manuscriptError.value = '请先创建或选择项目。'
      return
    }
    if (!title || !content) {
      manuscriptError.value = '请填写标题和正文后再保存。'
      return
    }
    if (manuscriptEditNeedsReview.value || manuscriptEditVersion.value === null) {
      manuscriptError.value = '请先核对当前正文并确认版本。你的编辑已保留。'
      return
    }

    const session = manuscriptEditSession
    const isCurrentEdit = () => session === manuscriptEditSession && isActiveProject(projectId)
    const snapshot = currentManuscriptEdits()
    persistDraft(manuscriptEditScopeKey(projectId, sceneId), snapshot)
    isSavingManuscriptScene.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/scenes/${sceneId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content, expected_scene_version: snapshot.expected_scene_version }),
      })
      if (!isCurrentEdit()) return
      if (response.status === 409) {
        manuscriptSaveConflict.value = true
        await refreshManuscriptEditConflict()
        return
      }
      if (!response.ok) {
        throw new Error('Could not save manuscript scene')
      }
      const updated: ManuscriptScene = await response.json()
      if (!isCurrentEdit()) {
        return
      }
      manuscriptScenes.value = manuscriptScenes.value.map((scene) =>
        scene.scene_id === updated.scene_id ? updated : scene
      )
      const unchanged = JSON.stringify(snapshot) === JSON.stringify(currentManuscriptEdits())
      // Advance the editor baseline without unmounting the textarea or losing
      // keystrokes made while this version was saving.
      hydratingManuscriptEdit = true
      manuscriptEditVersion.value = updated.version
      hydratingManuscriptEdit = false
      setBaseline(manuscriptEditScopeKey(projectId, sceneId), { ...snapshot, expected_scene_version: updated.version })
      if (unchanged) {
        clearDraft(manuscriptEditScopeKey(projectId, sceneId))
      } else {
        // Keep any input made while the request was in flight.
        persistDraft(manuscriptEditScopeKey(projectId, sceneId), currentManuscriptEdits())
      }
      invalidateHistoryOutput()
      const savedSession = manuscriptEditSession
      await refreshCommittedRevision(projectId)
      if (!isActiveProject(projectId) || savedSession !== manuscriptEditSession) {
        return
      }
      manuscriptStatus.value = unchanged ? `Scene saved as version ${updated.version}.`
        : `已保存 v${updated.version}；后续编辑已保留，尚未保存。`
    } catch {
      if (isCurrentEdit()) manuscriptError.value = '正文保存失败。你的编辑已保留，请检查 API 后重试。'
    } finally {
      if (session === manuscriptEditSession) isSavingManuscriptScene.value = false
    }
  }

  return {
    isSavingManuscriptScene,
    editingManuscriptSceneId,
    manuscriptEditTitle,
    manuscriptEditContent,
    manuscriptEditVersion,
    manuscriptEditNeedsReview,
    manuscriptEditReviewReady,
    isRefreshingManuscriptEdit,
    refreshManuscriptEditConflict,
    rebaseManuscriptSceneEdit,
    manuscriptEditScopeKey,
    currentManuscriptEdits,
    startEditingManuscriptScene,
    cancelEditingManuscriptScene,
    saveManuscriptSceneEdit,
  }
}
