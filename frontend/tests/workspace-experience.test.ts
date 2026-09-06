import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppearanceStore } from '../src/stores/appearance'
import { readLocation, writePreference } from '../src/services/preferences'
import {
  persistDraft,
  queueAutosave,
  setBaseline,
} from '../src/services/draftSessions'
import { useEditorSessionStore } from '../src/stores/editorSession'
import { loadDraft } from '../src/services/draftCache'
import { statusText } from '../src/utils/format'

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})
test('corrupt navigation preferences never navigate into an unknown workspace', () => {
  localStorage.setItem('ai-writing:ui:v1:location:a', '{broken')
  expect(readLocation('a')).toBeNull()
  writePreference('location:a', { section: 'unknown', scene: '', chapter: '' })
  expect(readLocation('a')).toBeNull()
  writePreference('location:a', {
    section: 'manuscript',
    scene: 's',
    chapter: 'c',
  })
  expect(readLocation('a')?.scene).toBe('s')
  expect(readLocation('b')).toBeNull()
})
test('appearance defaults survive invalid stored preferences', () => {
  writePreference('theme', 'purple')
  writePreference('fontSize', 600)
  const appearance = useAppearanceStore()
  expect(appearance.theme).toBe('light')
  expect(appearance.fontSize).toBe(18)
  expect(document.documentElement.dataset.theme).toBe('light')
})
test('local storage failure is visible and keeps the editor dirty', () => {
  const session = useEditorSessionStore()
  setBaseline('manuscript:a:s', { content: 'old' })
  vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
    throw new Error('quota')
  })
  persistDraft('manuscript:a:s', { content: 'new' })
  expect(session.draftState('manuscript:a:s')).toMatchObject({
    dirty: true,
    autosaveFailed: true,
  })
})
test('committing a version cancels queued snapshots of the old version', async () => {
  const key = 'manuscript:a:s'
  setBaseline(key, { content: 'old', version: 1 })
  queueAutosave(key, () => ({ content: 'new', version: 1 }))
  setBaseline(key, { content: 'new', version: 2 })
  await vi.runAllTimersAsync()
  expect(loadDraft(key)).toBeNull()
  expect(useEditorSessionStore().isDirty(key)).toBe(false)
})
test('status labels translate known states and retain unknown technical values', () => {
  expect(statusText('pending_review')).toBe('待审核')
  expect(statusText('custom_state')).toBe('custom state')
})
