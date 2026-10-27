<script setup lang="ts">
defineProps<{ title: string; description?: string; eyebrow?: string }>()
</script>

<template>
  <div class="page-heading">
    <div>
      <span v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</span>
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div class="page-actions"><slot /></div>
  </div>
</template>
