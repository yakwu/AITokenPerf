<template>
  <div class="compare-overlay" :class="{ open: show }" @click.self="$emit('close')">
    <div class="compare-modal" :style="maxWidth ? 'max-width:' + maxWidth : ''">
      <div class="compare-modal-header">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h2 style="margin:0">{{ title }}</h2>
          <button class="btn btn-ghost btn-sm" @click="$emit('close')" style="font-size:20px;line-height:1">&times;</button>
        </div>
      </div>
      <div class="compare-modal-body">
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  show: Boolean,
  title: { type: String, default: '' },
  maxWidth: { type: String, default: '' },
});

defineEmits(['close']);
</script>
