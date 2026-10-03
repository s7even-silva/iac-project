<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>();
</script>

<template>
  <section class="panel">
    <header class="head">
      <h2>{{ title }}</h2>
      <p v-if="subtitle">{{ subtitle }}</p>
    </header>
    <div class="body"><slot /></div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  min-width: 0;
}
.head {
  background: var(--panel-head);
  border-bottom: 1px solid var(--line);
  padding: 0.7rem 1rem;
  position: relative;
}
.head::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.7rem;
  bottom: 0.7rem;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--shield);
}
h2 { margin: 0; font-size: 1.05rem; font-weight: 650; letter-spacing: -0.01em; }
p { margin: 0.15rem 0 0; font-size: 0.85rem; color: var(--ink-2); }
.body { padding: 0.8rem 1rem 1rem; }
</style>
