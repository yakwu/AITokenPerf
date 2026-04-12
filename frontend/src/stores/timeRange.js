import { defineStore } from 'pinia';
import { ref, watch } from 'vue';

const STORAGE_KEY = 'aitokenperf_time_range';
const DEFAULT_HOURS = 6;
const VALID_VALUES = [6, 24, 168, null];

export const useTimeRangeStore = defineStore('timeRange', () => {
  // 从 localStorage 恢复
  let initial = DEFAULT_HOURS;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved !== null) {
      const parsed = JSON.parse(saved);
      if (VALID_VALUES.includes(parsed)) initial = parsed;
    }
  } catch { /* ignore */ }

  const hours = ref(initial);

  const options = [
    { label: '6h', value: 6 },
    { label: '24h', value: 24 },
    { label: '7d', value: 168 },
    { label: '全部', value: null },
  ];

  function setHours(val) {
    if (VALID_VALUES.includes(val)) {
      hours.value = val;
    }
  }

  // 持久化到 localStorage
  watch(hours, (v) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
  });

  return { hours, options, setHours };
});
