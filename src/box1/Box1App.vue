<script setup lang="ts">
import { computed, ref } from "vue";
import PanelCard from "../components/PanelCard.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import RangeField from "../components/RangeField.vue";
import SourceIcon from "../components/SourceIcon.vue";
import TrajectoryView from "./TrajectoryView.vue";
import RigiditySpectrum from "./RigiditySpectrum.vue";
import TurnedBackBars from "./TurnedBackBars.vue";
import { C, SPECIES, energyAt, fmtE, fmtLen, fmtR, rigidity, type SpeciesKey } from "../lib/physics";
import { SPECTRA, fractionBelow } from "../lib/spectra";

const L = 2; // field layer thickness, m
const SYMBOL: Record<SpeciesKey, string> = { p: "p", He: "He", Fe: "Fe" };

const sp = ref<SpeciesKey>("p");
const logT = ref(3); // log10 kinetic energy per nucleon, MeV
const B = ref(2); // T
const compare = ref(false);

const speciesOptions = (Object.keys(SPECIES) as SpeciesKey[]).map(k => ({ value: k, label: SPECIES[k].label }));

const tn = computed(() => 10 ** logT.value);
const R = computed(() => rigidity(sp.value, tn.value));
const r = computed(() => R.value / (C * B.value));
const Rcut = computed(() => C * B.value * L);
const fate = computed(() => {
  if (r.value <= L) return "turned back";
  const deg = (Math.asin(L / r.value) * 180) / Math.PI;
  return `bent ${deg.toFixed(deg < 10 ? 1 : 0)}°`;
});
const energyLabel = computed(() =>
  sp.value === "p" ? fmtE(tn.value) : `${fmtE(tn.value)}/n`,
);

const partner = computed<SpeciesKey>(() => (sp.value === "Fe" ? "p" : "Fe"));
const partnerEnergy = computed(() => {
  const t = energyAt(partner.value, R.value);
  return fmtE(t * SPECIES[partner.value].A);
});

const lcut = computed(() => Math.log10(Rcut.value));
const bars = computed(() => [
  { label: "SEP", kind: "sun" as const, f: fractionBelow(SPECTRA.sep, lcut.value) },
  { label: "GCR p", kind: "galaxy" as const, f: fractionBelow(SPECTRA.gcr_h, lcut.value) },
  { label: "GCR He", kind: "galaxy" as const, dashed: true, f: fractionBelow(SPECTRA.gcr_he, lcut.value) },
]);
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>Rigidity, not energy, decides what the field turns back</h1>
      <span class="pill num">R = p / Ze</span>
    </header>

    <main class="grid">
      <PanelCard title="Path in a 2 m field layer">
        <div class="viz-wrap">
          <TrajectoryView :R="R" :B="B" :compare="compare" class="viz" />
          <div class="badges">
            <span class="badge"><b class="num">{{ fmtR(R) }}</b></span>
            <span class="badge">r = <b class="num">{{ fmtLen(r) }}</b></span>
            <span class="badge" :class="{ hit: r <= L }">{{ fate }}</span>
            <span v-if="compare" class="badge cmp"><i class="dash" />{{ SYMBOL[partner] }} · <b class="num">{{ partnerEnergy }}</b> · same path</span>
          </div>
        </div>

        <div class="controls">
          <div class="line">
            <SegmentedControl v-model="sp" :options="speciesOptions" label="Particle" />
            <label class="toggle">
              <input v-model="compare" type="checkbox" />
              <span class="knob" />
              <span>{{ SYMBOL[partner] }} at same R</span>
            </label>
          </div>
          <RangeField id="energy" v-model="logT" label="Energy" :min="1" :max="5" :step="0.01" :display="energyLabel" />
          <RangeField id="field" v-model="B" label="Field B" :min="0.5" :max="10" :step="0.1" :display="`${B.toFixed(1)} T`" />
        </div>
      </PanelCard>

      <PanelCard title="Who gets turned back">
        <ul class="legend">
          <li><SourceIcon kind="sun" />SEP · Oct 1989</li>
          <li><SourceIcon kind="galaxy" />GCR protons</li>
          <li><SourceIcon kind="galaxy" dashed />GCR helium</li>
        </ul>
        <RigiditySpectrum :R="R" :Rcut="Rcut" :symbol="SYMBOL[sp]" class="viz" />
        <TurnedBackBars :rows="bars" class="bars" />
      </PanelCard>
    </main>

    <footer>Uniform 2 m layer, illustrative · Spectra: OLTARIS, BON2020 solar min. and Oct 1989 SPE, above 10 MeV/n</footer>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 1rem; }
.hero { display: flex; align-items: center; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 0.9rem; }
h1 { margin: 0; font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; }
.pill {
  border: 1px solid var(--shield); color: var(--shield); border-radius: 999px;
  padding: 0.15rem 0.7rem; font-size: 0.9rem; background: var(--shield-soft);
}
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 780px) { .grid { grid-template-columns: 1fr; } }
.viz { max-height: 50vh; }
.viz-wrap { position: relative; }
.badges { position: absolute; top: 0.4rem; right: 0.4rem; display: flex; flex-direction: column; align-items: flex-end; gap: 0.3rem; }
.badge {
  background: var(--panel-head); border: 1px solid var(--line); border-radius: 999px;
  padding: 0.15rem 0.6rem; font-size: 0.8rem; color: var(--ink-2); white-space: nowrap;
}
.badge b { color: var(--ink); font-weight: 600; }
.badge.hit { color: var(--bg); background: var(--shield); border-color: var(--shield); font-weight: 650; }
.badge.cmp { border-color: var(--gcr); }
.dash { display: inline-block; width: 14px; border-top: 3px dashed var(--gcr); margin-right: 0.4rem; vertical-align: middle; }
.controls { display: grid; gap: 0.55rem; margin-top: 0.6rem; }
.line { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
.toggle { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--ink-2); cursor: pointer; }
.toggle input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.knob {
  width: 36px; height: 20px; border-radius: 999px; background: var(--bg); border: 1px solid var(--line-strong);
  position: relative; transition: background-color var(--dur) var(--ease);
}
.knob::after {
  content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%;
  background: var(--ink-2); transition: transform var(--dur) var(--ease), background-color var(--dur) var(--ease);
}
.toggle input:checked + .knob { background: var(--gcr); border-color: var(--gcr); }
.toggle input:checked + .knob::after { transform: translateX(16px); background: var(--ink); }
.toggle input:focus-visible + .knob { outline: 2px solid var(--shield); outline-offset: 2px; }
.legend { list-style: none; display: flex; flex-wrap: wrap; gap: 0.4rem 1.1rem; margin: 0 0 0.2rem; padding: 0; font-size: 0.82rem; color: var(--ink-2); }
.legend li { display: inline-flex; align-items: center; gap: 0.4rem; }
.bars { margin-top: 0.6rem; }
footer { margin-top: 0.8rem; font-size: 0.72rem; color: var(--ink-3); }
</style>
