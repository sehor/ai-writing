import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { fetchApi } from '../src/api/client'
import { useSnowflakeStore } from '../src/stores/snowflake'
import type { SnowflakeRecordRevision } from '../src/types'

const workspace = vi.hoisted(() => ({
  activeProjectId: 'novel',
  activeProject: { id: 'novel', premise: 'A premise.' },
  activeStepNumber: 6,
  activeStep: { number: 6, optional: false },
}))

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
vi.mock('../src/stores/workspace', () => ({ useWorkspaceStore: () => workspace }))

const currentRecord = {
  id: 'record-revision-101',
  project_id: 'novel',
  step_number: 6,
  record_id: 'block-101',
  position: 101,
  revision_no: 1,
  source: 'human',
  status: 'accepted',
  payload: { record_id: 'block-101' },
  base_revision_id: '',
  review_reason: '',
  created_at: 'now',
  reviewed_at: 'now',
} satisfies SnowflakeRecordRevision

const pendingRecord = {
  ...currentRecord,
  id: 'record-revision-102',
  revision_no: 2,
  source: 'ai',
  status: 'pending_review',
  base_revision_id: currentRecord.id,
} satisfies SnowflakeRecordRevision

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.mocked(fetchApi).mockReset()
})

test('targeted generation sends record IDs and loads pending record revisions for review', async () => {
  vi.mocked(fetchApi).mockImplementation(async (path, options) => {
    if (path.endsWith('/snowflake/generations')) {
      const body = JSON.parse(String(options?.body))
      expect(body.target_record_ids).toEqual(['block-101'])
      expect(body.generation_mode).toBe('selection')
      return Response.json({
        project_id: 'novel',
        step_number: 6,
        artifact: 'expanded_plot',
        content: '{"records":[]}',
        workflow_trace: [],
        revision: null,
        record_revisions: [pendingRecord],
      }, { status: 201 })
    }
    if (path.includes('/snowflake/steps/6/records')) {
      return Response.json({
        data: [pendingRecord],
        page: 1,
        page_size: 50,
        total_items: 101,
        total_pages: 3,
      })
    }
    throw new Error(`Unexpected request: ${path}`)
  })

  const store = useSnowflakeStore()
  store.records = [currentRecord]
  store.generationInstruction = 'Strengthen the selected sequence.'
  store.generationMode = 'selection'
  store.toggleRecordSelection('block-101')

  await store.generateArtifact()

  expect(store.records).toEqual([pendingRecord])
  expect(store.revisions).toEqual([])
  expect(store.artifactStatus).toContain('pending revision')
})

test('a newer pending revision still selects the accepted head by record ID', () => {
  const store = useSnowflakeStore()
  store.records = [pendingRecord]

  store.toggleRecordSelection('block-101')

  expect(store.selectedRecordIds).toEqual(['block-101'])
})

test('legacy selection is imported as a pending manuscript proposal', async () => {
  const proposal = {
    id: 'legacy-proposal',
    project_id: 'novel',
    scene_id: 'scene-1',
    source: 'legacy_snowflake_import',
    title: 'Recovered scene',
    content: 'Selected legacy prose.',
    context: 'Human selection.',
    checklist: [],
    status: 'pending_review',
    created_at: 'now',
    reviewed_at: '',
  }
  vi.mocked(fetchApi).mockImplementation(async (path, options) => {
    if (path.includes('/from-legacy-snowflake/')) {
      expect(JSON.parse(String(options?.body))).toEqual({
        scene_id: 'scene-1',
        title: 'Recovered scene',
        content: 'Selected legacy prose.',
      })
      return Response.json(proposal, { status: 201 })
    }
    if (path.endsWith('/manuscript/proposals')) return Response.json([proposal])
    throw new Error(`Unexpected request: ${path}`)
  })

  const store = useSnowflakeStore()
  const imported = await store.importLegacyDraftSelection(
    'legacy-step-10',
    'scene-1',
    'Recovered scene',
    'Selected legacy prose.',
  )

  expect(imported.source).toBe('legacy_snowflake_import')
  expect(imported.status).toBe('pending_review')
  expect(store.artifactStatus).toContain('pending Manuscript proposal')
})
