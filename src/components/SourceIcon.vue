<script setup lang="ts">
// Glyphs for the two radiation sources: the Sun (SEP) and the galaxy (GCR).
defineProps<{ kind: "sun" | "galaxy"; size?: number; dashed?: boolean }>();
</script>

<template>
  <svg
    :width="size ?? 18"
    :height="size ?? 18"
    :style="{ width: `${size ?? 18}px`, height: `${size ?? 18}px` }"
    viewBox="-12 -12 24 24"
    aria-hidden="true"
    class="icon"
  >
    <g v-if="kind === 'sun'" class="sun">
      <circle r="4.5" />
      <path
        d="M0 -10.5V-7.5M0 7.5V10.5M-10.5 0H-7.5M7.5 0H10.5M-7.4 -7.4L-5.3 -5.3M5.3 5.3L7.4 7.4M-7.4 7.4L-5.3 5.3M5.3 -5.3L7.4 -7.4"
      />
    </g>
    <g v-else class="galaxy" :class="{ dashed }">
      <path d="M0 0C3-1 4 2 2 4C-1 6-5 3-5 0C-5-5 1-8 5-6C9-4 10 2 7 6" />
      <path d="M0 0C-3 1-4-2-2-4C1-6 5-3 5 0C5 5-1 8-5 6C-9 4-10-2-7-6" />
      <circle r="1.6" />
    </g>
  </svg>
</template>

<style scoped>
.icon { flex: none; overflow: visible; }
.sun circle { fill: var(--sep); }
.sun path { stroke: var(--sep); stroke-width: 2; stroke-linecap: round; }
.galaxy path { fill: none; stroke: var(--gcr); stroke-width: 1.8; stroke-linecap: round; }
.galaxy.dashed path { stroke-dasharray: 2.5 2.5; }
.galaxy circle { fill: var(--gcr); }
</style>
