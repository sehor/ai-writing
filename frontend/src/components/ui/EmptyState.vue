<script setup lang="ts">
import AppIcon from './AppIcon.vue'
defineProps<{ title: string; description?: string; icon?: string }>()
</script>
<template>
  <div class="workspace-empty">
    <AppIcon :name="icon ?? 'book'" :size="32" />
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>
