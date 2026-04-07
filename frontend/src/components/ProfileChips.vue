<template>
  <div class="profile-chips" style="margin-top:4px">
    <button
      v-for="p in profiles" :key="p"
      class="profile-chip"
      :class="{ active: isSelected(p) }"
      @click="toggle(p)"
      style="width:auto;min-width:100px"
    >
      <span class="profile-chip-name" style="font-size:13px">{{ p }}</span>
      <span v-show="isSelected(p)" class="profile-chip-check" style="font-size:12px">&#10003;</span>
    </button>
  </div>
</template>

<script setup>
const props = defineProps({
  profiles: { type: Array, default: () => [] },
  selected: { type: Array, default: () => [] },
});

const emit = defineEmits(['update:selected']);

function isSelected(name) {
  return props.selected.includes(name);
}

function toggle(name) {
  const arr = props.selected;
  if (arr.includes(name)) {
    emit('update:selected', arr.filter(n => n !== name));
  } else {
    emit('update:selected', [...arr, name]);
  }
}
</script>
