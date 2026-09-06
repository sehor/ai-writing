<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
const paths: Record<string, string> = {
  snowflake: 'M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9M9 4l3 3 3-3M9 20l3-3 3 3',
  book: 'M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1ZM12 5v15',
  feather: 'M4 20l12-12M7 17C2 10 10 2 21 3c1 11-7 19-14 14ZM9 15h7',
  graph:
    'M6 6l12 12M6 18L18 6M8 5h8M5 8v8M19 8v8M8 19h8M7 3H3v4h4V3ZM21 3h-4v4h4V3ZM7 17H3v4h4v-4ZM21 17h-4v4h4v-4Z',
  edit: 'M15 5l4 4M4 20l4-1L21 6l-4-4L4 15v5ZM12 20h8',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'M6 6l12 12M6 18L18 6',
  sun: 'M12 3v2M12 19v2M3 12h2M19 12h2M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  moon: 'M20 15A8 8 0 0 1 9 4a8.5 8.5 0 1 0 11 11Z',
  settings: 'M4 7h16M4 17h16M8 4v6M16 14v6',
  folder: 'M3 7V4h6l3 3h9v13H3V7Z',
  chevron: 'M9 5l7 7-7 7',
  plus: 'M12 5v14M5 12h14',
  focus: 'M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5',
  panel: 'M3 4h18v16H3V4ZM15 4v16',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM15 15l6 6',
}
</script>
<template>
  <svg
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] ?? paths.book" />
  </svg>
</template>
