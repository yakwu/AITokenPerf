<template>
  <div class="inline-notifier-create">
    <button v-if="!open" type="button" class="inc-toggle" @click="open = true">＋ 新建渠道</button>
    <div v-else class="inc-form">
      <input class="form-input" v-model.trim="name" placeholder="渠道名（如 运维群飞书）" autocomplete="off">
      <input class="form-input" v-model.trim="webhook" placeholder="飞书 Webhook URL" autocomplete="off">
      <div class="inc-actions">
        <button type="button" class="btn btn-primary btn-sm" :disabled="saving" @click="onCreate">{{ saving ? '创建中...' : '创建' }}</button>
        <button type="button" class="btn btn-ghost btn-sm" @click="cancel">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { createNotifierApi } from '../api/index.js';
import { toast } from '../composables/useToast.js';

const emit = defineEmits(['created']);
const open = ref(false);
const name = ref('');
const webhook = ref('');
const saving = ref(false);

function reset() { name.value = ''; webhook.value = ''; open.value = false; }
function cancel() { reset(); }

async function onCreate() {
  if (!name.value) { toast('渠道名不能为空', 'error'); return; }
  if (!webhook.value) { toast('Webhook 不能为空', 'error'); return; }
  saving.value = true;
  try {
    const res = await createNotifierApi({ name: name.value, webhook: webhook.value });
    if (res && res.error) { toast(res.error, 'error'); return; }
    toast('告警渠道已创建', 'success');
    emit('created');
    reset();
  } catch (e) { toast(e?.message || '创建失败', 'error'); }
  finally { saving.value = false; }
}
</script>

<style scoped>
.inline-notifier-create { margin-top: 8px; }
.inc-toggle { background: none; border: 1px dashed var(--border); border-radius: var(--radius); color: var(--accent); cursor: pointer; font-size: 12px; padding: 6px 12px; }
.inc-toggle:hover { background: var(--bg); }
.inc-form { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); max-width: 420px; }
.inc-actions { display: flex; gap: 8px; }
</style>
