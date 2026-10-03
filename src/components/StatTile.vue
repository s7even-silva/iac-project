<script setup lang="ts">
defineProps<{ label: string; value: string; swatch?: string; dashed?: boolean }>();
</script>

<template>
  <div class="stat">
    <div class="k">
      <span v-if="swatch" class="sw" :class="{ dashed }" :style="{ borderColor: swatch }" />
      {{ label }}
    </div>
    <div class="v num">{{ value }}</div>
  </div>
</template>

<style scoped>
.stat {
  background: var(--sunken);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 0.45rem 0.7rem;
  min-width: 0;
}
.k { display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--ink-2); }
.v { font-size: 1.3rem; font-weight: 600; margin-top: 0.1rem; white-space: nowrap; }
.sw { width: 14px; border-top: 3px solid; border-radius: 2px; flex: none; }
.sw.dashed { border-top-style: dashed; }
</style>
