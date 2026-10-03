<script setup lang="ts" generic="T extends string">
defineProps<{ options: { value: T; label: string }[]; label: string }>();
const model = defineModel<T>({ required: true });
</script>

<template>
  <div class="seg" role="radiogroup" :aria-label="label">
    <button
      v-for="o in options"
      :key="o.value"
      role="radio"
      :aria-checked="model === o.value"
      :class="{ on: model === o.value }"
      @click="model = o.value"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.seg {
  display: inline-flex;
  padding: 3px;
  gap: 3px;
  background: var(--sunken);
  border: 1px solid var(--line);
  border-radius: 10px;
}
button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font-size: 0.88rem;
  font-weight: 550;
  padding: 0.4rem 0.85rem;
  min-height: 36px;
  border-radius: 7px;
  transition: background-color var(--dur) var(--ease), color var(--dur) var(--ease);
}
button:hover { color: var(--ink); background: var(--panel-head); }
button.on { background: var(--shield); color: #0B1220; }
</style>
