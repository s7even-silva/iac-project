<script setup lang="ts">
import SourceIcon from "../components/SourceIcon.vue";
import { fmtPct } from "../lib/physics";

// One bar per source: the share of its particles the layer turns back.
defineProps<{ rows: { label: string; kind: "sun" | "galaxy"; dashed?: boolean; f: number }[] }>();
</script>

<template>
  <div class="bars">
    <div v-for="r in rows" :key="r.label" class="row">
      <SourceIcon :kind="r.kind" :dashed="r.dashed" :size="18" />
      <span class="name">{{ r.label }}</span>
      <span class="track"><span class="fill" :style="{ width: `${Math.max(1.5, r.f * 100)}%` }" /></span>
      <span class="val num">{{ fmtPct(r.f) }}</span>
    </div>
  </div>
</template>

<style scoped>
.bars { display: grid; gap: 0.45rem; }
.row { display: grid; grid-template-columns: 18px 5.2em 1fr 4.8em; align-items: center; gap: 0.6rem; }
.name { font-size: 0.85rem; color: var(--ink-2); }
.track { height: 10px; border-radius: 999px; background: var(--bg); border: 1px solid var(--line); overflow: hidden; }
.fill {
  display: block; height: 100%; border-radius: 999px; background: var(--shield);
  transition: width 240ms var(--ease);
}
.val { text-align: right; font-weight: 600; }
</style>
