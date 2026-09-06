import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { readPreference, writePreference } from '../services/preferences'

export const useAppearanceStore = defineStore('appearance', () => {
  const theme = ref(
    readPreference<string>('theme', 'light') === 'dark' ? 'dark' : 'light',
  )
  const savedSize = readPreference<number>('fontSize', 18)
  const fontSize = ref([16, 18, 20, 22].includes(savedSize) ? savedSize : 18)
  const focus = ref(false)
  const navigationOpen = ref(false)
  watch(
    theme,
    (value) => {
      document.documentElement.dataset.theme = value
      writePreference('theme', value)
    },
    { immediate: true },
  )
  watch(
    fontSize,
    (value) => {
      document.documentElement.style.setProperty(
        '--editor-font-size',
        `${value}px`,
      )
      writePreference('fontSize', value)
    },
    { immediate: true },
  )
  return { theme, fontSize, focus, navigationOpen }
})
