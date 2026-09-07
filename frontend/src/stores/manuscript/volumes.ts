import { ref, watch } from 'vue'
import { useProjectContextStore } from '../projectContext'
import { useEditorSessionStore } from '../editorSession'
import { fetchApi } from '../../api/client'
import { readErrorDetail } from '../../api/errors'
import { confirmLeave } from '../../composables/useDirtyGuard'
import { acknowledgeDraftSave, discardSavedScope, isScopeDirty, persistDraft, queueAutosave, restoreCachedDraft, setBaseline } from '../../services/draftSessions'
import type { ManuscriptVolume, VolumeDraft } from '../../types/volume'

/** Created once by the manuscript facade. Organization never owns prose or its versions. */
export function useManuscriptVolumes() {
  const context = useProjectContextStore()
  const session = useEditorSessionStore()
  const manuscriptVolumes = ref<ManuscriptVolume[]>([])
  const activeVolumeId = ref('')
  const volumeDraft = ref<VolumeDraft>({ title: '', sequence: 1 })
  const volumeError = ref('')
  const volumeStatus = ref('')
  const isLoadingVolumes = ref(false)
  const isSavingVolume = ref(false)
  let draftProjectId = ''
  let epoch = 0
  let loadEpoch = 0
  let hydrating = false
  const snapshot = () => ({ ...volumeDraft.value })
  const volumeScopeKey = () => `volume:${draftProjectId}:${activeVolumeId.value || 'new'}`
  const current = (project: string, token: number) => project === context.activeProjectId && token === epoch
  const sorted = (items: ManuscriptVolume[]) => items.sort((a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id))

  watch(volumeDraft, () => {
    if (!hydrating && draftProjectId) queueAutosave(volumeScopeKey(), snapshot)
  }, { deep: true, flush: 'sync' })

  function persistVolumeDraft() {
    if (isScopeDirty(volumeScopeKey(), snapshot())) persistDraft(volumeScopeKey(), snapshot())
  }
  function hydrate(id: string) {
    hydrating = true
    activeVolumeId.value = id
    const record = manuscriptVolumes.value.find(item => item.id === id)
    const initial = record ? { title: record.title, sequence: record.sequence } : { title: '', sequence: 1 }
    setBaseline(volumeScopeKey(), initial)
    const cached = restoreCachedDraft<VolumeDraft>(volumeScopeKey())
    const value = cached?.value
    volumeDraft.value = value && typeof value.title === 'string' && Number.isInteger(value.sequence) ? { ...value } : initial
    if (isScopeDirty(volumeScopeKey(), snapshot())) {
      session.markDirty(volumeScopeKey(), cached?.savedAt)
      volumeStatus.value = '已恢复本地卷草稿，尚未保存。'
    }
    hydrating = false
  }
  function selectVolume(id: string) {
    if (isSavingVolume.value || (id && !manuscriptVolumes.value.some(v => v.id === id))) return
    if (draftProjectId === context.activeProjectId && id === activeVolumeId.value) return
    if (!confirmLeave(volumeScopeKey(), '卷编辑')) return
    persistVolumeDraft()
    epoch++
    draftProjectId = context.activeProjectId
    volumeError.value = ''; volumeStatus.value = ''
    hydrate(id)
  }
  function resetVolumes() {
    persistVolumeDraft()
    session.dropEditor(volumeScopeKey())
    epoch++; loadEpoch++
    hydrating = true
    draftProjectId = ''; activeVolumeId.value = ''; manuscriptVolumes.value = []
    volumeDraft.value = { title: '', sequence: 1 }
    volumeError.value = ''; volumeStatus.value = ''
    isLoadingVolumes.value = false; isSavingVolume.value = false
    hydrating = false
  }
  async function loadManuscriptVolumes(project = context.activeProjectId) {
    if (!project || isSavingVolume.value) return
    const token = ++loadEpoch
    isLoadingVolumes.value = true; volumeError.value = ''
    try {
      const response = await fetchApi(`/projects/${project}/manuscript/volumes`)
      if (!response.ok) throw new Error('卷目录加载失败，请刷新重试。')
      const values: ManuscriptVolume[] = await response.json()
      if (project !== context.activeProjectId || token !== loadEpoch) return
      if (!Array.isArray(values)) throw new Error('卷目录格式无效。')
      manuscriptVolumes.value = sorted(values)
      if (draftProjectId !== project) { draftProjectId = project; hydrate('') }
    } catch (error) {
      if (project === context.activeProjectId && token === loadEpoch) volumeError.value = error instanceof Error ? error.message : '卷目录加载失败。'
    } finally {
      if (token === loadEpoch) isLoadingVolumes.value = false
    }
  }
  async function checked(response: Response) {
    if (!response.ok) {
      const detail = await readErrorDetail(response)
      throw new Error(detail.message || '卷组织保存失败，请刷新核对后重试。')
    }
    return response
  }
  async function saveVolume() {
    if (isSavingVolume.value || isLoadingVolumes.value || !draftProjectId || draftProjectId !== context.activeProjectId) return
    volumeError.value = ''; volumeStatus.value = ''
    const value = snapshot()
    if (!value.title.trim() || value.title.trim().length > 160 || !Number.isInteger(value.sequence) || value.sequence < 1 || value.sequence > 999) {
      volumeError.value = '请填写卷名（1–160 字）及 1–999 的排序号。'; return
    }
    const project = draftProjectId, id = activeVolumeId.value, token = epoch, key = volumeScopeKey()
    persistVolumeDraft()
    isSavingVolume.value = true
    try {
      const response = await checked(await fetchApi(`/projects/${project}/manuscript/volumes${id ? `/${id}` : ''}`, {
        method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value),
      }))
      const saved: ManuscriptVolume = await response.json()
      if (!current(project, token)) return
      manuscriptVolumes.value = sorted([...manuscriptVolumes.value.filter(v => v.id !== saved.id), saved])
      const latest = snapshot()
      acknowledgeDraftSave(key, value, latest)
      if (!id) {
        discardSavedScope(key, { title: '', sequence: 1 })
        activeVolumeId.value = saved.id
        acknowledgeDraftSave(volumeScopeKey(), value, latest)
      }
      volumeStatus.value = '卷已保存；正文及叙事时点未改变。'
    } catch (error) {
      if (current(project, token)) volumeError.value = error instanceof Error ? error.message : '卷保存失败。'
    } finally { if (current(project, token)) isSavingVolume.value = false }
  }
  async function deleteVolume() {
    if (isSavingVolume.value || isLoadingVolumes.value || !activeVolumeId.value || draftProjectId !== context.activeProjectId) return
    if (!window.confirm('删除此卷？章节将移到“未分卷”，章、场景和正文版本均保留。')) return
    const project = draftProjectId, id = activeVolumeId.value, token = epoch
    isSavingVolume.value = true; volumeError.value = ''
    try {
      await checked(await fetchApi(`/projects/${project}/manuscript/volumes/${id}`, { method: 'DELETE' }))
      if (!current(project, token)) return
      discardSavedScope(volumeScopeKey(), snapshot())
      manuscriptVolumes.value = manuscriptVolumes.value.filter(v => v.id !== id)
      hydrate(''); volumeStatus.value = '卷已删除；所属章节保留在未分卷中。'
    } catch (error) {
      if (current(project, token)) volumeError.value = error instanceof Error ? error.message : '卷删除失败。'
    } finally { if (current(project, token)) isSavingVolume.value = false }
  }
  async function assignChapterVolume(chapterId: string, volumeId: string) {
    if (isSavingVolume.value || isLoadingVolumes.value || !context.activeProjectId) return
    const project = context.activeProjectId, token = epoch
    isSavingVolume.value = true; volumeError.value = ''
    try {
      await checked(await fetchApi(`/projects/${project}/manuscript/chapters/${chapterId}/volume`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ volume_id: volumeId }),
      }))
      if (!current(project, token)) return
      manuscriptVolumes.value = manuscriptVolumes.value.map(v => ({ ...v,
        chapter_ids: [...v.chapter_ids.filter(id => id !== chapterId), ...(v.id === volumeId ? [chapterId] : [])],
      }))
      volumeStatus.value = '章节归属已保存；场景时序和正文版本未改变。'
    } catch (error) {
      if (current(project, token)) volumeError.value = error instanceof Error ? error.message : '章节归卷失败。'
    } finally { if (current(project, token)) isSavingVolume.value = false }
  }
  const volumeDraftSnapshotEntries = (): Array<[string, () => unknown]> => draftProjectId ? [[volumeScopeKey(), snapshot]] : []
  return { manuscriptVolumes, activeVolumeId, volumeDraft, volumeError, volumeStatus, isLoadingVolumes, isSavingVolume,
    volumeScopeKey, selectVolume, saveVolume, deleteVolume, assignChapterVolume, loadManuscriptVolumes, resetVolumes, volumeDraftSnapshotEntries }
}
