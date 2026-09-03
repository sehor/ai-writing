import { beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { fetchApi } from '../src/api/client'
import { useProjectsStore } from '../src/stores/projects'

const { workspace } = vi.hoisted(() => ({
  workspace: { activeProjectId: 'demo-novel' },
}))

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }))
vi.mock('../src/stores/workspace', () => ({ useWorkspaceStore: () => workspace }))

beforeEach(() => {
  setActivePinia(createPinia())
  workspace.activeProjectId = 'demo-novel'
  vi.mocked(fetchApi).mockReset()
})

test('successful project creation gives explicit feedback and opens the project', async () => {
  const created = {
    id: 'project',
    title: '妖行记',
    premise: '一个人类剑客与体内狐妖灵魂的冒险故事。',
    current_step: 1,
  }
  vi.mocked(fetchApi).mockResolvedValueOnce(Response.json(created, { status: 201 }))

  const projects = useProjectsStore()
  projects.newProject = { title: ` ${created.title} `, premise: ` ${created.premise} ` }

  await projects.createProject()

  expect(fetchApi).toHaveBeenCalledWith('/projects', expect.objectContaining({ method: 'POST' }))
  expect(projects.projects).toEqual([created])
  expect(workspace.activeProjectId).toBe(created.id)
  expect(projects.newProject).toEqual({ title: '', premise: '' })
  expect(projects.createStatus).toBe(`Project "${created.title}" created successfully.`)
  expect(projects.createError).toBe('')
})

test('a new submit clears stale success feedback before validation', async () => {
  const projects = useProjectsStore()
  projects.createStatus = 'Project created.'

  await projects.createProject()

  expect(projects.createStatus).toBe('')
  expect(projects.createError).toBe('Title and premise are required.')
  expect(fetchApi).not.toHaveBeenCalled()
})
