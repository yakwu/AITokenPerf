<template>
  <template v-if="active">
    <button class="btn btn-danger btn-sm" @click="$emit('confirm')">确认</button>
    <button class="btn btn-ghost btn-sm" @click="$emit('cancel')">取消</button>
  </template>
  <template v-else>
    <button class="btn btn-ghost btn-sm" :title="title" :style="iconStyle" @click="$emit('request')">
      <slot>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
      </slot>
    </button>
  </template>
</template>

<script setup>
defineProps({
  active: Boolean,
  title: { type: String, default: '删除' },
  iconStyle: { type: String, default: '' },
});

defineEmits(['confirm', 'cancel', 'request']);
</script>
