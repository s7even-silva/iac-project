<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { C } from "../lib/physics";

const props = defineProps<{ R: number; B: number; compare: boolean }>();

const L = 2; // field layer thickness, m
const W = 600, H = 300;
const S = 64, X0 = -1.2, Y0 = -0.35, XMAX = 8.2, YMAX = 4.3; // px per m and world window
const px = (x: number) => (x - X0) * S;
const py = (y: number) => H - (y - Y0) * S;

const crosses: { x: number; y: number }[] = [];
for (let x = 0.33; x < L; x += 0.67) for (let y = 0.3; y < YMAX - 0.4; y += 0.6) crosses.push({ x: px(x), y: py(y) });

/** Path of a positive particle entering at (X0, 0) along +x, field into the page. */
const path = computed(() => {
  const r = props.R / (C * props.B);
  let d = `M${px(X0)} ${py(0)} L${px(0)} ${py(0)}`;
  if (r <= L) {
    // Semicircle back out of the entry face, as two quarter arcs.
    d += ` A${r * S} ${r * S} 0 0 0 ${px(r)} ${py(r)}`;
    d += ` A${r * S} ${r * S} 0 0 0 ${px(0)} ${py(2 * r)}`;
    d += ` L${px(X0)} ${py(2 * r)}`;
    return { d, r, turned: true, theta: Math.PI };
  }
  const yExit = r - Math.sqrt(r * r - L * L);
  const theta = Math.asin(L / r);
  d += ` A${r * S} ${r * S} 0 0 0 ${px(L)} ${py(yExit)}`;
  const dx = Math.cos(theta), dy = Math.sin(theta);
  const t = Math.min((XMAX - L) / dx, (YMAX - yExit) / dy);
  d += ` L${px(L + dx * t)} ${py(yExit + dy * t)}`;
  return { d, r, turned: false, theta };
});

// A dot travels along the path so the bend reads as motion, not as a static line.
const pathEl = ref<SVGPathElement | null>(null);
const dot = ref({ x: px(X0), y: py(0) });
let raf = 0;
let start = 0;
const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

function tick(now: number) {
  const el = pathEl.value;
  if (el) {
    const len = el.getTotalLength();
    const f = ((now - start) / 2600) % 1;
    const p = el.getPointAtLength(f * len);
    dot.value = { x: p.x, y: p.y };
  }
  raf = requestAnimationFrame(tick);
}
onMounted(() => {
  if (!reduced) raf = requestAnimationFrame(tick);
});
onBeforeUnmount(() => cancelAnimationFrame(raf));
watch(path, () => (start = performance.now()));
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="Particle path through a uniform magnetic field layer">

    <rect :x="px(0)" y="0" :width="L * S" :height="H" class="slab" />
    <line :x1="px(0)" :x2="px(0)" y1="0" :y2="H" class="edge" />
    <line :x1="px(L)" :x2="px(L)" y1="0" :y2="H" class="edge" />
    <g class="cross">
      <g v-for="(c, i) in crosses" :key="i" :transform="`translate(${c.x} ${c.y})`">
        <circle r="5" />
        <path d="M-3.5 -3.5 L3.5 3.5 M3.5 -3.5 L-3.5 3.5" />
      </g>
    </g>
    <text :x="px(L / 2)" y="20" text-anchor="middle" class="lab-field">B into the page</text>
    <text :x="px(L / 2)" :y="H - 8" text-anchor="middle" class="lab-dim">2 m</text>

    <rect :x="px(4)" :y="py(3.4)" :width="3 * S" :height="3 * S" rx="16" class="habitat" />
    <text :x="px(5.5)" :y="py(1.9)" text-anchor="middle" class="lab-hab">Habitat</text>

    <path ref="pathEl" :d="path.d" class="track" />
    <path v-if="compare" :d="path.d" class="track-cmp" />
    <circle :cx="px(X0)" :cy="py(0)" r="5" class="origin" />
    <circle v-if="!reduced" :cx="dot.x" :cy="dot.y" r="5" class="particle" />
  </svg>
</template>

<style scoped>
.slab { fill: var(--shield-soft); }
.edge { stroke: var(--shield); stroke-opacity: 0.45; }
.cross circle { fill: none; stroke: var(--shield); stroke-opacity: 0.45; }
.cross path { stroke: var(--shield); stroke-opacity: 0.45; }
.lab-field { fill: var(--shield); font-size: 15px; font-weight: 550; }
.lab-dim { fill: var(--ink-3); font-size: 13px; }
.habitat { fill: var(--panel-head); stroke: var(--line-strong); }
.lab-hab { fill: var(--ink-2); font-size: 17px; font-weight: 500; }
.track { fill: none; stroke: var(--ink); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.track-cmp { fill: none; stroke: var(--gcr); stroke-width: 3.5; stroke-dasharray: 8 7; stroke-linecap: round; }
.origin { fill: var(--ink); stroke: var(--panel); stroke-width: 2; }
.particle { fill: var(--ink); stroke: var(--panel); stroke-width: 2; }
</style>
