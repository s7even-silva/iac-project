<script setup lang="ts">
import { computed, ref } from "vue";
import { scaleLinear, scaleLog } from "d3-scale";
import { curveMonotoneX, line } from "d3-shape";
import { SPECTRA, interp, type Spectrum } from "../lib/spectra";
import { fmtR } from "../lib/physics";
import SourceIcon from "../components/SourceIcon.vue";

const props = defineProps<{ R: number; Rcut: number; symbol: string }>();

const W = 600, H = 300;
const M = { l: 56, r: 34, t: 30, b: 46 };
const R_MIN = 0.1, R_MAX = 1000, Y_MAX = 360;
const x = scaleLog().domain([R_MIN, R_MAX]).range([M.l, W - M.r]).clamp(true);
const y = scaleLinear().domain([0, Y_MAX]).range([H - M.b, M.t]);
const yTicks = [0, 60, 120, 180, 240, 300, 360];
const xTicks = [0.1, 1, 10, 100, 1000];

interface Series { key: keyof typeof SPECTRA; color: string; short: string; dashed: boolean }
const series: Series[] = [
  { key: "sep", color: "var(--sep)", short: "SEP", dashed: false },
  { key: "gcr_h", color: "var(--gcr)", short: "GCR p", dashed: false },
  { key: "gcr_he", color: "var(--gcr-2)", short: "GCR He", dashed: true },
];

const gen = line<[number, number]>().x(d => x(d[0])).y(d => y(d[1])).curve(curveMonotoneX);
const pathOf = (s: Spectrum) =>
  gen(
    s.log10_R_GV.map((lr, i) => [10 ** lr, s.pct_per_decade[i]] as [number, number])
      .filter(([r]) => r >= R_MIN && r <= R_MAX),
  ) ?? "";
const paths = series.map(s => ({ ...s, d: pathOf(SPECTRA[s.key]) }));

const cutX = computed(() => x(props.Rcut));
const markX = computed(() => x(props.R));

// Hover: crosshair and the three values at that rigidity.
const svgEl = ref<SVGSVGElement | null>(null);
const hover = ref<{ vx: number; R: number; left: number; top: number } | null>(null);
function onMove(ev: PointerEvent) {
  const box = svgEl.value!.getBoundingClientRect();
  const vx = ((ev.clientX - box.left) / box.width) * W;
  if (vx < M.l || vx > W - M.r) return (hover.value = null);
  const R = x.invert(vx);
  let left = ev.clientX - box.left + 14;
  if (left > box.width - 180) left -= 200;
  hover.value = { vx, R, left, top: ev.clientY - box.top - 12 };
}
const hoverRows = computed(() =>
  hover.value
    ? series.map(s => ({ ...s, v: interp(SPECTRA[s.key], "pct_per_decade", Math.log10(hover.value!.R)) }))
    : [],
);
</script>

<template>
  <div class="wrap">
    <svg
      ref="svgEl"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      aria-label="Rigidity distribution of SEP and GCR particles, with the cutoff of the field layer"
      @pointermove="onMove"
      @pointerleave="hover = null"
    >
      <rect :x="M.l" :y="M.t" :width="Math.max(0, cutX - M.l)" :height="H - M.t - M.b" class="wash" />
      <line :x1="cutX" :x2="cutX" :y1="M.t" :y2="H - M.b" class="cut" />
      <text :x="cutX - 6" :y="M.t - 10" text-anchor="end" class="cut-lab num">cutoff {{ fmtR(Rcut) }}</text>

      <g class="axis">
        <g v-for="t in yTicks" :key="t">
          <line :x1="M.l" :x2="W - M.r" :y1="y(t)" :y2="y(t)" class="grid" />
          <text :x="M.l - 8" :y="y(t) + 4" text-anchor="end">{{ t }}%</text>
        </g>
        <text v-for="t in xTicks" :key="t" :x="x(t)" :y="H - M.b + 18" text-anchor="middle">{{ t }} GV</text>
        <text :x="(M.l + W - M.r) / 2" :y="H - 6" text-anchor="middle">Rigidity (log scale)</text>
      </g>
      <line :x1="M.l" :x2="W - M.r" :y1="y(0)" :y2="y(0)" class="base" />

      <path
        v-for="p in paths"
        :key="p.key"
        :d="p.d"
        class="curve"
        :style="{ stroke: p.color }"
        :stroke-dasharray="p.dashed ? '7 5' : undefined"
      />
      <SourceIcon kind="sun" :size="22" :x="x(10 ** -0.78) + 6" :y="y(345) - 11" />
      <SourceIcon kind="galaxy" :size="22" :x="x(10 ** 0.165) - 30" :y="y(124) - 11" />
      <SourceIcon kind="galaxy" dashed :size="22" :x="x(10 ** 0.36) + 8" :y="y(124) - 11" />

      <line :x1="markX" :x2="markX" :y1="M.t" :y2="H - M.b" class="mark" />
      <circle :cx="markX" :cy="M.t + 2" r="12" class="mark-dot" />
      <text :x="markX" :y="M.t + 6.5" text-anchor="middle" class="mark-lab">{{ symbol }}</text>

      <line v-if="hover" :x1="hover.vx" :x2="hover.vx" :y1="M.t" :y2="H - M.b" class="hover" />
    </svg>
    <div v-if="hover" class="tip" :style="{ left: `${hover.left}px`, top: `${hover.top}px` }">
      <div class="num"><b>{{ fmtR(hover.R) }}</b></div>
      <div v-for="r in hoverRows" :key="r.key" class="row">
        <span class="sw" :class="{ dashed: r.dashed }" :style="{ borderColor: r.color }" />
        {{ r.short }}
        <span class="num">{{ r.v === null ? "–" : `${r.v.toFixed(1)}%` }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { position: relative; }
.wash { fill: var(--shield-soft); }
.cut { stroke: var(--shield); stroke-opacity: 0.7; stroke-width: 1.5; }
.cut-lab { fill: var(--shield); font-size: 14px; font-weight: 550; }
.axis text { fill: var(--ink-2); font-size: 14px; }
.grid { stroke: var(--line); }
.base { stroke: var(--line-strong); }
.curve { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.mark { stroke: var(--ink); stroke-width: 2; }
.mark-dot { fill: var(--ink); }
.mark-lab { fill: var(--bg); font-size: 12px; font-weight: 700; }
.hover { stroke: var(--ink-3); }
.tip {
  position: absolute;
  pointer-events: none;
  background: var(--panel-head);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 0.35rem 0.55rem;
  font-size: 0.8rem;
  white-space: nowrap;
}
.row { display: flex; align-items: center; gap: 0.4rem; }
.row .num { margin-left: auto; padding-left: 0.8rem; }
.sw { width: 14px; border-top: 3px solid; border-radius: 2px; }
.sw.dashed { border-top-style: dashed; }
</style>
