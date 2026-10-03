<script setup lang="ts">
defineProps<{ id: string; label: string; min: number; max: number; step: number; display: string }>();
const model = defineModel<number>({ required: true });
</script>

<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <input
      :id="id"
      v-model.number="model"
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :style="{ '--fill': `${((model - min) / (max - min)) * 100}%` }"
    />
    <output :for="id" class="num">{{ display }}</output>
  </div>
</template>

<style scoped>
.field { display: grid; grid-template-columns: 4.8em 1fr 9.5em; align-items: center; gap: 0.75rem; }
label { font-size: 0.85rem; color: var(--ink-2); }
output { font-weight: 600; font-size: 0.95rem; }
input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--shield) var(--fill), var(--line-strong) var(--fill));
  cursor: pointer;
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--ink);
  border: 3px solid var(--shield);
  box-shadow: 0 0 10px var(--shield-glow);
}
input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--ink);
  border: 3px solid var(--shield);
  box-shadow: 0 0 10px var(--shield-glow);
}
</style>
