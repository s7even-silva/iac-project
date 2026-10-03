<script setup lang="ts">
import { computed, ref } from "vue";
import PanelCard from "../components/PanelCard.vue";
import StatTile from "../components/StatTile.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import RangeField from "../components/RangeField.vue";
import TrajectoryView from "./TrajectoryView.vue";
import RigiditySpectrum from "./RigiditySpectrum.vue";
import { C, SPECIES, energyAt, fmtE, fmtLen, fmtPct, fmtR, rigidity, type SpeciesKey } from "../lib/physics";
import { SPECTRA, fractionBelow } from "../lib/spectra";

const L = 2; // field layer thickness, m

const sp = ref<SpeciesKey>("p");
const logT = ref(3); // log10 kinetic energy per nucleon, MeV
const B = ref(2); // T
const compare = ref(false);

const speciesOptions = (Object.keys(SPECIES) as SpeciesKey[]).map(k => ({ value: k, label: SPECIES[k].label }));
const presets = [
  { label: "Solar proton · 100 MeV", set: { sp: "p" as SpeciesKey, logT: 2, B: 2, compare: false } },
  { label: "Cosmic-ray proton · 2 GeV", set: { sp: "p" as SpeciesKey, logT: Math.log10(2000), B: 2, compare: false } },
  { label: "10 GeV proton vs iron", set: { sp: "p" as SpeciesKey, logT: 4, B: 2, compare: true } },
];
function apply(p: (typeof presets)[number]["set"]) {
  sp.value = p.sp; logT.value = p.logT; B.value = p.B; compare.value = p.compare;
}

const tn = computed(() => 10 ** logT.value);
const R = computed(() => rigidity(sp.value, tn.value));
const r = computed(() => R.value / (C * B.value));
const Rcut = computed(() => C * B.value * L);
const fate = computed(() => {
  if (r.value <= L) return "Turned back";
  const deg = (Math.asin(L / r.value) * 180) / Math.PI;
  return `Bent ${deg.toFixed(deg < 10 ? 1 : 0)}°`;
});
const energyLabel = computed(() =>
  sp.value === "p" ? fmtE(tn.value) : `${fmtE(tn.value)}/n · ${fmtE(tn.value * SPECIES[sp.value].A)}`,
);

const partner = computed<SpeciesKey>(() => (sp.value === "Fe" ? "p" : "Fe"));
const compareText = computed(() => {
  const t = energyAt(partner.value, R.value);
  return partner.value === "Fe"
    ? `Iron-56 at ${fmtE(t)} per nucleon (${fmtE(t * 56)} in total) has the same rigidity, so it follows the same path.`
    : `A proton at ${fmtE(t)} has the same rigidity, so it follows the same path.`;
});

const lcut = computed(() => Math.log10(Rcut.value));
const turned = computed(() => ({
  sep: fmtPct(fractionBelow(SPECTRA.sep, lcut.value)),
  h: fmtPct(fractionBelow(SPECTRA.gcr_h, lcut.value)),
  he: fmtPct(fractionBelow(SPECTRA.gcr_he, lcut.value)),
}));
</script>

<template>
  <div class="page">
    <header class="hero">
      <p class="eyebrow">Why active shielding</p>
      <h1>A magnet sorts particles by rigidity, not by energy</h1>
      <p class="lede">
        Rigidity <span class="num">R = p / Ze</span> is momentum per unit charge. Particles with the same rigidity
        follow the same path in the same field.
      </p>
    </header>

    <main class="grid">
      <PanelCard title="Path through a 2 m layer of uniform field" subtitle="An illustration of the physics, not the CREW HaT field (that is Box 2).">
        <TrajectoryView :R="R" :B="B" :compare="compare" class="viz" />

        <div class="controls">
          <div class="line">
            <SegmentedControl v-model="sp" :options="speciesOptions" label="Particle" />
            <label class="check">
              <input v-model="compare" type="checkbox" />
              <span>Overlay {{ partner === "Fe" ? "iron-56" : "a proton" }} at the same rigidity</span>
            </label>
          </div>
          <RangeField id="energy" v-model="logT" label="Energy" :min="1" :max="5" :step="0.01" :display="energyLabel" />
          <RangeField id="field" v-model="B" label="Field B" :min="0.5" :max="10" :step="0.1" :display="`${B.toFixed(1)} T`" />
          <div class="chips" aria-label="Examples">
            <button v-for="p in presets" :key="p.label" class="chip" @click="apply(p.set)">{{ p.label }}</button>
          </div>
        </div>

        <div class="stats">
          <StatTile label="Rigidity" :value="fmtR(R)" />
          <StatTile label="Radius of curvature" :value="fmtLen(r)" />
          <StatTile label="In this layer" :value="fate" />
        </div>
        <p v-if="compare" class="note"><span class="sw" />{{ compareText }}</p>
      </PanelCard>

      <PanelCard title="Where the incoming particles are" subtitle="Share of particles per decade of rigidity, above 10 MeV/n. Shaded: what the layer turns back.">
        <ul class="legend">
          <li><span class="sw" style="border-color: var(--sep)" />SEP protons, Oct 1989</li>
          <li><span class="sw" style="border-color: var(--gcr)" />GCR protons, solar min.</li>
          <li><span class="sw dashed" style="border-color: var(--gcr-2)" />GCR helium, solar min.</li>
        </ul>
        <RigiditySpectrum :R="R" :Rcut="Rcut" :particle-name="SPECIES[sp].name" class="viz" />
        <div class="stats">
          <StatTile label="SEP protons turned back" :value="turned.sep" swatch="var(--sep)" />
          <StatTile label="GCR protons turned back" :value="turned.h" swatch="var(--gcr)" />
          <StatTile label="GCR helium turned back" :value="turned.he" swatch="var(--gcr-2)" dashed />
        </div>
        <p class="note">
          In this uniform layer only. Inside a real shield, part of the flux arrives from directions the field cannot
          block, and secondaries add dose.
        </p>
      </PanelCard>
    </main>

    <footer>
      Spectra: NASA OLTARIS, Badhwar–O'Neill 2020 (free space, 31 Dec 2019) and Historical SPE (October 1989).
      Radius of curvature r = R / (cB); turned back when r ≤ 2 m, i.e. R ≤ 0.6 · B[T] GV. · IAC-26,A1,IPB,42
    </footer>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 1rem; }
.hero { margin-bottom: 0.9rem; }
.eyebrow {
  margin: 0; color: var(--shield); font-size: 0.75rem; font-weight: 650;
  letter-spacing: 0.12em; text-transform: uppercase;
}
h1 { margin: 0.15rem 0 0.25rem; font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; }
.lede { margin: 0; color: var(--ink-2); max-width: 70ch; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 780px) { .grid { grid-template-columns: 1fr; } }
.viz { max-height: 38vh; }
.controls { display: grid; gap: 0.55rem; margin-top: 0.7rem; }
.line { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
.check { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--ink-2); cursor: pointer; }
.check input { width: 18px; height: 18px; accent-color: var(--gcr); cursor: pointer; }
.chips { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.chip {
  background: transparent; border: 1px solid var(--line-strong); color: var(--ink-2);
  border-radius: 999px; padding: 0.3rem 0.75rem; min-height: 32px; font-size: 0.8rem;
  transition: border-color var(--dur) var(--ease), color var(--dur) var(--ease), background-color var(--dur) var(--ease);
}
.chip:hover { border-color: var(--shield); color: var(--shield); background: var(--shield-soft); }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-top: 0.75rem; }
.note { margin: 0.6rem 0 0; font-size: 0.82rem; color: var(--ink-2); }
.legend { list-style: none; display: flex; flex-wrap: wrap; gap: 0.4rem 1rem; margin: 0 0 0.3rem; padding: 0; font-size: 0.82rem; color: var(--ink-2); }
.legend li { display: inline-flex; align-items: center; gap: 0.4rem; }
.sw { display: inline-block; width: 16px; border-top: 3px solid var(--gcr); border-radius: 2px; margin-right: 0.4rem; vertical-align: middle; }
.note .sw { border-top-style: dashed; }
.legend .sw { margin-right: 0; }
.sw.dashed { border-top-style: dashed; }
footer { margin-top: 0.9rem; font-size: 0.75rem; color: var(--ink-3); }
</style>
