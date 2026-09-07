import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useBackupsStore } from '../src/stores/backups'
import { fetchApi } from '../src/api/client'

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
vi.mock('../src/stores/projectContext', () => ({ useProjectContextStore: () => ({
  activeProjectId: 'novel', activeProject: { id: 'novel', title: 'Novel' },
  reloadActiveProject: vi.fn(),
}) }))

beforeEach(() => { setActivePinia(createPinia()); vi.mocked(fetchApi).mockReset() })

const preview = (overrides = {}) => ({
  project: { id: 'novel', title: 'Novel', row_counts: { projects: 1 } },
  target_exists: true, can_overwrite: true, legacy_incomplete: false,
  format_version: 2, warnings: [], ...overrides,
})

test('legacy backup cannot overwrite even when the checkbox is confirmed', async () => {
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json(preview({
    can_overwrite: false, legacy_incomplete: true, format_version: 1,
  })))
  const backups = useBackupsStore()
  await backups.previewImportPackage(new File(['zip'], 'legacy.zip'))
  backups.overwriteConfirmed = true
  await backups.importPreviewedPackage()
  expect(fetchApi).toHaveBeenCalledTimes(1)
  expect(backups.importError).toContain('不能覆盖')
})

test('v2 overwrite sends the exact previewed file only after confirmation', async () => {
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json(preview()))
  const backups = useBackupsStore()
  const file = new File(['zip'], 'backup.zip')
  await backups.previewImportPackage(file)
  await backups.importPreviewedPackage()
  expect(fetchApi).toHaveBeenCalledTimes(1)
  backups.overwriteConfirmed = true
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json({ project: preview().project, replaced_existing: true }))
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json([]))
  await backups.importPreviewedPackage()
  expect(fetchApi).toHaveBeenCalledWith('/projects/backups/import?overwrite=true', expect.objectContaining({ body: file }))
  expect(backups.preview).toBeNull()
})

test('invalid previews and discarded packages cannot be imported', async () => {
  const backups = useBackupsStore()
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json({ detail: 'Unsafe path' }, { status: 400 }))
  await backups.previewImportPackage(new File(['bad'], 'bad.zip'))
  await backups.importPreviewedPackage()
  expect(fetchApi).toHaveBeenCalledTimes(1)
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json(preview()))
  await backups.previewImportPackage(new File(['zip'], 'valid.zip'))
  backups.discardPreview()
  await backups.importPreviewedPackage()
  expect(fetchApi).toHaveBeenCalledTimes(2)
})

test('a late preview cannot replace a newer package or resurrect a discarded package', async () => {
  let finishOld!: (value: Response) => void
  vi.mocked(fetchApi).mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve }))
  const backups = useBackupsStore()
  const old = backups.previewImportPackage(new File(['old'], 'old.zip'))
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json(preview({ format_version: 2 })))
  await backups.previewImportPackage(new File(['new'], 'new.zip'))
  finishOld(Response.json(preview({ format_version: 1, can_overwrite: false })))
  await old
  expect(backups.importFileName).toBe('new.zip')
  expect(backups.preview?.format_version).toBe(2)
  let finishDiscarded!: (value: Response) => void
  vi.mocked(fetchApi).mockReturnValueOnce(new Promise((resolve) => { finishDiscarded = resolve }))
  const discarded = backups.previewImportPackage(new File(['discard'], 'discard.zip'))
  backups.discardPreview()
  finishDiscarded(Response.json(preview()))
  await discarded
  expect(backups.preview).toBeNull()
  expect(backups.isLoadingPreview).toBe(false)
})
