<template>
  <div class="filter-dropdown" :class="{ 'filter-dropdown--wide': wide }" ref="rootRef">
    <button class="filter-dropdown-btn" @click.stop="open = !open">
      <span>{{ displayLabel }}</span>
      <svg width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 1l4 4 4-4"/></svg>
    </button>
    <div class="filter-dropdown-list" v-show="open">
      <div class="combobox-option" :class="{ active: !modelValue }" @mousedown.prevent="select('')">{{ allLabel }}</div>
      <div v-for="opt in options" :key="opt" class="combobox-option" :class="{ active: modelValue === opt }" @mousedown.prevent="select(opt)">{{ opt }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  allLabel: { type: String, default: '全部' },
  wide: { type: Boolean, default: false },
});

const emit = defineEmits(['update:modelValue']);

const open = ref(false);
const rootRef = ref(null);

function select(val) {
  emit('update:modelValue', val);
  open.value = false;
}

function handleClickOutside(e) {
  if (rootRef.value && !rootRef.value.contains(e.target)) {
    open.value = false;
  }
}

const displayLabel = ref('');
import { watch } from 'vue';
watch(() => [props.modelValue, props.options], () => {
  displayLabel.value = props.modelValue || props.allLabel;
}, { immediate: true });

onMounted(() => document.addEventListener('click', handleClickOutside));
onUnmounted(() => document.removeEventListener('click', handleClickOutside));
</script>
