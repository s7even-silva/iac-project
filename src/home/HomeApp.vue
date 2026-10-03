<script setup lang="ts">
import PanelCard from "../components/PanelCard.vue";

const base = import.meta.env.BASE_URL;
const boxes = [
  { n: 1, title: "Why active shielding", text: "Rigidity explorer: particle paths in a field layer and the SEP and GCR rigidity spectra.", href: `${base}box1/` },
  { n: 2, title: "CREW HaT design", text: "In preparation." },
  { n: 3, title: "Simulation and first results", text: "In preparation." },
  { n: 4, title: "The audit and where we stand", text: "In preparation." },
];
</script>

<template>
  <div class="page">
    <header>
      <p class="eyebrow">IAC 2026 · IAC-26,A1,IPB,42</p>
      <h1>Active HTS magnetic shielding: interactive content</h1>
      <p class="lede">Each box of the iPoster embeds one of these pages.</p>
    </header>
    <main class="grid">
      <PanelCard v-for="b in boxes" :key="b.n" :title="`Box ${b.n} · ${b.title}`">
        <p class="text">{{ b.text }}</p>
        <a v-if="b.href" :href="b.href" class="open">Open</a>
      </PanelCard>
    </main>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 1.5rem 1rem; }
.eyebrow { margin: 0; color: var(--shield); font-size: 0.75rem; font-weight: 650; letter-spacing: 0.12em; text-transform: uppercase; }
h1 { margin: 0.2rem 0 0.3rem; font-size: 1.7rem; letter-spacing: -0.02em; }
.lede { margin: 0 0 1rem; color: var(--ink-2); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }
.text { margin: 0 0 0.7rem; color: var(--ink-2); font-size: 0.9rem; }
.open {
  display: inline-block; color: #04111f; background: var(--shield); border-radius: 8px;
  padding: 0.35rem 0.9rem; font-weight: 650; text-decoration: none; font-size: 0.85rem;
}
.open:hover { box-shadow: 0 0 14px var(--shield-glow); }
</style>
