<template>
  <div class="model-selector">
    <!-- Vendor Filter Chips -->
    <div v-if="vendorFilter && vendors.length" class="filter-chips">
      <button
        class="filter-chip"
        :class="{ active: activeVendor === '' }"
        @click="activeVendor = ''"
      >全部</button>
      <button
        v-for="v in vendors"
        :key="v.id"
        class="filter-chip"
        :class="{ active: activeVendor === v.id }"
        @click="activeVendor = v.id"
      >{{ v.name }}</button>
    </div>

    <!-- Tags + Combobox -->
    <div class="combobox" ref="comboboxRef">
      <div class="model-tags-input" @click.stop="dropdownOpen = true">
        <span v-for="(m, i) in modelValue" :key="m" class="model-tag">
          {{ m }}
          <button type="button" class="model-tag-remove" @click.stop="removeModel(i)">&times;</button>
        </span>
        <input
          ref="searchInputRef"
          class="model-tag-search"
          v-model="searchText"
          :placeholder="modelValue.length ? '' : placeholder"
          @focus="dropdownOpen = true"
          @keydown.enter.prevent="onEnter"
          @keydown.backspace="onBackspace"
          @keydown.escape="dropdownOpen = false"
          autocomplete="off"
        >
      </div>
      <button
        class="combobox-toggle"
        type="button"
        @click.stop="dropdownOpen = !dropdownOpen"
        @mousedown.prevent
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
      </button>
      <div class="combobox-dropdown" v-show="dropdownOpen">
        <div
          v-for="m in filteredModels"
          :key="m.id"
          class="combobox-option"
          :class="{ active: modelValue.includes(m.id) }"
          @mousedown.prevent="selectModel(m.id)"
        >{{ m.id }}</div>
        <div class="combobox-empty" v-show="!filteredModels.length && searchText && allowCustom">
          无匹配，按回车添加「{{ searchText }}」
        </div>
        <div class="combobox-empty" v-show="!filteredModels.length && searchText && !allowCustom">
          无匹配模型
        </div>
        <div class="combobox-empty" v-show="!filteredModels.length && !searchText && !loading">
          暂无模型数据
        </div>
        <div class="combobox-empty" v-show="loading">
          加载中...
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { getPricingModels, getVendors } from '../api';

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  vendorFilter: { type: Boolean, default: true },
  allowCustom: { type: Boolean, default: true },
  placeholder: { type: String, default: '搜索或选择模型' },
});

const emit = defineEmits(['update:modelValue']);

const comboboxRef = ref(null);
const searchInputRef = ref(null);
const dropdownOpen = ref(false);
const searchText = ref('');
const activeVendor = ref('');
const loading = ref(false);

const allModels = ref([]);
const vendors = ref([]);

async function loadData() {
  loading.value = true;
  try {
    const [modelsRes, vendorsRes] = await Promise.all([
      getPricingModels('', true),
      getVendors(),
    ]);
    allModels.value = modelsRes.models || [];
    vendors.value = vendorsRes.vendors || [];
  } catch {
    allModels.value = [];
    vendors.value = [];
  }
  loading.value = false;
}

onMounted(loadData);

const filteredModels = computed(() => {
  let list = allModels.value;

  // Filter by vendor
  if (activeVendor.value) {
    list = list.filter(m => m.vendor === activeVendor.value);
  }

  // Exclude already selected
  list = list.filter(m => !props.modelValue.includes(m.id));

  // Filter by search text
  const q = (searchText.value || '').toLowerCase();
  if (q) {
    list = list.filter(m => m.id.toLowerCase().includes(q));
  }

  return list;
});

function selectModel(id) {
  if (!props.modelValue.includes(id)) {
    emit('update:modelValue', [...props.modelValue, id]);
  }
  searchText.value = '';
}

function removeModel(index) {
  const updated = [...props.modelValue];
  updated.splice(index, 1);
  emit('update:modelValue', updated);
}

function onEnter() {
  if (filteredModels.value.length) {
    selectModel(filteredModels.value[0].id);
    return;
  }
  if (props.allowCustom && searchText.value.trim()) {
    const val = searchText.value.trim();
    if (!props.modelValue.includes(val)) {
      emit('update:modelValue', [...props.modelValue, val]);
    }
    searchText.value = '';
  }
}

function onBackspace() {
  if (!searchText.value && props.modelValue.length) {
    const updated = [...props.modelValue];
    updated.pop();
    emit('update:modelValue', updated);
  }
}

// Click outside
function handleClickOutside(e) {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target)) {
    dropdownOpen.value = false;
  }
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside));
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside));
</script>

<style scoped>
.model-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.model-selector .filter-chips {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
