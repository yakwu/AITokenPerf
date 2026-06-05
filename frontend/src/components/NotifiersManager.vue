<template>
  <div class="notifiers-manager">
    <div class="nm-header">
      <h3>告警器</h3>
      <button class="btn btn-primary" @click="openCreate">新建告警器</button>
    </div>
    <div v-if="items.length === 0" class="form-hint">还没有告警器，点「新建」添加一个飞书机器人。</div>
    <ul class="nm-list">
      <li v-for="n in items" :key="n.id" class="nm-item">
        <div class="nm-meta">
          <span class="nm-name">{{ n.name }}</span>
          <span class="nm-type">{{ n.type }}</span>
          <span class="nm-webhook">{{ n.webhook }}</span>
        </div>
        <div class="nm-actions">
          <button class="btn btn-ghost" :disabled="testingId === n.id" @click="onTest(n)">{{ testingId === n.id ? '发送中...' : '测试' }}</button>
          <button class="btn btn-ghost" @click="openEdit(n)">编辑</button>
          <button class="btn btn-ghost" @click="onDelete(n)">删除</button>
        </div>
      </li>
    </ul>

    <div v-if="showForm" class="nm-form">
      <div class="form-group">
        <label class="form-label">名称</label>
        <input class="form-input" v-model.trim="form.name" placeholder="运维群飞书">
      </div>
      <div class="form-group">
        <label class="form-label">飞书 Webhook URL</label>
        <input class="form-input" v-model.trim="form.webhook" :placeholder="editingId ? '留空 = 不修改' : 'https://open.feishu.cn/open-apis/bot/v2/hook/...'">
      </div>
      <div class="btn-group">
        <button class="btn btn-primary" :disabled="saving" @click="onSave">保存</button>
        <button class="btn btn-ghost" @click="closeForm">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getNotifiers, createNotifierApi, updateNotifierApi, deleteNotifierApi, notifierTestApi } from '../api/index.js';
import { toast } from '../composables/useToast.js';

const items = ref([]);
const showForm = ref(false);
const editingId = ref(null);
const saving = ref(false);
const testingId = ref(null);
const form = ref({ name: '', webhook: '' });

async function load() {
  try { items.value = await getNotifiers(); } catch (e) { toast('加载告警器失败', 'error'); }
}
function openCreate() { editingId.value = null; form.value = { name: '', webhook: '' }; showForm.value = true; }
function openEdit(n) { editingId.value = n.id; form.value = { name: n.name, webhook: '' }; showForm.value = true; }
function closeForm() { showForm.value = false; }

async function onSave() {
  if (!form.value.name) { toast('名称不能为空', 'error'); return; }
  saving.value = true;
  try {
    const res = editingId.value
      ? await updateNotifierApi(editingId.value, { name: form.value.name, webhook: form.value.webhook })
      : await createNotifierApi({ name: form.value.name, webhook: form.value.webhook });
    if (res && res.error) { toast(res.error, 'error'); return; }
    showForm.value = false;
    await load();
    toast('已保存', 'success');
  } catch (e) { toast(e?.message || '保存失败', 'error'); }
  finally { saving.value = false; }
}

async function onTest(n) {
  testingId.value = n.id;
  try { const r = await notifierTestApi(n.id); toast(r.ok ? '测试消息已发送' : '发送失败', r.ok ? 'success' : 'error'); }
  catch (e) { toast('发送失败', 'error'); }
  finally { testingId.value = null; }
}

async function onDelete(n) {
  if (!confirm(`删除告警器「${n.name}」？`)) return;
  try {
    const res = await deleteNotifierApi(n.id);
    if (res && res.error) { toast(res.error, 'error'); return; }
    await load();
    toast('已删除', 'success');
  } catch (e) { toast(e?.message || '删除失败', 'error'); }
}

onMounted(load);
defineExpose({ load });
</script>

<style scoped>
.nm-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.nm-header h3 { margin: 0; font-size: 16px; }
.nm-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.nm-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border: 1px solid var(--border, #e5e7eb); border-radius: 8px; }
.nm-meta { display: flex; align-items: center; gap: 12px; min-width: 0; flex-wrap: wrap; }
.nm-name { font-weight: 600; }
.nm-type { font-size: 12px; opacity: 0.6; }
.nm-webhook { font-size: 12px; opacity: 0.7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nm-actions { display: flex; gap: 8px; flex-shrink: 0; }
.nm-form { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border, #e5e7eb); max-width: 500px; display: flex; flex-direction: column; gap: 12px; }
</style>
