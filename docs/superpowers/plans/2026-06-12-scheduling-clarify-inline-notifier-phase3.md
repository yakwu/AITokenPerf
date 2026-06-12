# 定时任务澄清 + 告警渠道就地新建 · 阶段三 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps use checkbox。

**Goal:** 完成 IA 重构最后一阶段：①「持续监控」(`SiteSchedulesTab`) 配告警处可**就地新建告警渠道**（不必跳设置页），复用 `createNotifierApi`；②顶栏「定时任务」(`TasksView`) 降级为**跨站点只读总览 + 轻操作**（暂停/恢复/立即跑/删除），**去掉创建**——创建/编辑统一回站点「持续监控」，并加文案讲清两者关系。落实设计稿 §7/§142-144。

**Architecture:** 纯前端。新增可复用组件 `InlineNotifierCreate.vue`（折叠按钮→内联 名称+webhook 表单→`createNotifierApi`→emit `created`）；`SiteSchedulesTab` 在 create 表单与 edit 弹窗的告警器下拉旁各挂一个，`created` 后重载告警器列表并自动选中**最新（id 最大）**那个。`TasksView` 删除新建入口与创建弹窗及相关脚本，保留列表/筛选/轻操作，加澄清文案。

**Tech Stack:** Vue 3 + Pinia；构建 `bun run build`，前端用 **bun**。

**工作目录：** `/Users/yakun/linkingrid/AITokenPerf/.claude/worktrees/issue-58-overview-health-board`（分支 `feat/issue-58-overview-health-board`）。

**关联设计：** §7（定时任务澄清 + 告警就地新建）、§142（定时任务只读总览，不在此创建）、§143（两者关系=看板↔详情，文案讲清）、§144（告警渠道就地新建，复用 NotifiersManager 能力）。

**契约（实现者须知）：**
- `createNotifierApi({ name, webhook })`（type 服务端默认飞书）；name、webhook 均必填（参照 `NotifiersManager.vue` onSave）。返回若含 `.error` 即失败。
- 创建后**自动选中**：重载 `getNotifiers()`，选 `id` 最大的（刚建的最新），写入对应表单的 `alert_notifier_id`。
- `SiteSchedulesTab` 已有 `notifiers` ref + `loadNotifiers()`；create 与 edit 各有独立 `alert_notifier_id`。

---

## File Structure
- **Create** `frontend/src/components/InlineNotifierCreate.vue`：内联「＋新建渠道」组件，emit `created`。
- **Modify** `frontend/src/components/SiteSchedulesTab.vue`：create 表单 + edit 弹窗各接入该组件 + `onNotifierCreated` 处理 + 文案更新。
- **Modify** `frontend/src/views/TasksView.vue`：删创建入口/弹窗/相关脚本，加澄清文案，简化 `loadData`。

---

## Task 1: 就地新建渠道组件 + 接入持续监控

**Files:** Create `frontend/src/components/InlineNotifierCreate.vue`；Modify `frontend/src/components/SiteSchedulesTab.vue`

- [ ] **Step 1: 新建 InlineNotifierCreate.vue** — 创建 `frontend/src/components/InlineNotifierCreate.vue`：
```vue
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
```

- [ ] **Step 2: SiteSchedulesTab 导入组件** — 在 `frontend/src/components/SiteSchedulesTab.vue` 的 import 区（`import ModalOverlay from './ModalOverlay.vue';` 之后，约 349 行）加：
```js
import InlineNotifierCreate from './InlineNotifierCreate.vue';
```

- [ ] **Step 3: create 表单接入** — 在 create 表单的告警器 form-group 里，把这段（约 115 行）：
```html
              <div class="form-hint">在「设置」页管理告警器</div>
```
替换为：
```html
              <div class="form-hint">选择已有告警渠道，或就地新建一个</div>
              <InlineNotifierCreate @created="onNotifierCreated('create')" />
```

- [ ] **Step 4: edit 弹窗接入** — 在 edit 弹窗的告警器 form-group 里，把这段（约 314 行）：
```html
            <div class="form-hint">在「设置」页管理告警器</div>
```
替换为：
```html
            <div class="form-hint">选择已有告警渠道，或就地新建一个</div>
            <InlineNotifierCreate @created="onNotifierCreated('edit')" />
```

- [ ] **Step 5: 加 onNotifierCreated 处理** — 在 `<script setup>` 里 `loadNotifiers` 函数之后（约 361 行后）加：
```js
async function onNotifierCreated(target) {
  await loadNotifiers();
  if (!notifiers.value.length) return;
  const newest = notifiers.value.reduce((a, b) => (b.id > a.id ? b : a));
  if (target === 'edit') editForm.value.alert_notifier_id = newest.id;
  else createForm.value.alert_notifier_id = newest.id;
}
```

- [ ] **Step 6: 构建** — `cd frontend && bun run build`，必须成功。

- [ ] **Step 7: 提交**
```bash
git add frontend/src/components/InlineNotifierCreate.vue frontend/src/components/SiteSchedulesTab.vue
git commit -m "feat(web): 持续监控配告警处支持就地新建告警渠道 (#58)"
```

---

## Task 2: 定时任务页改只读总览

**Files:** Modify `frontend/src/views/TasksView.vue`

> 目标：去掉「新建任务」入口与创建弹窗，定时任务页只做**跨站点总览 + 轻操作**（暂停/恢复/立即跑/删除）。**保留**：toolbar 的搜索/状态筛选/计数、调度表格、`filteredSchedules`、`pause/resume/runNow/confirmDelete`、`InlineConfirmDelete`、`store.refreshFn = loadData`、route watch。**删除**：新建按钮、整个创建 `ModalOverlay`、所有仅服务于创建的脚本与 import。加澄清文案。

- [ ] **Step 1: 删「新建任务」按钮 + 加澄清文案** — 把 toolbar 右侧整块（约 21–26 行）：
```html
      <div class="sites-toolbar-right">
        <button class="btn btn-primary btn-sm" @click="onCreateTask">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建任务
        </button>
      </div>
```
替换为：
```html
      <div class="sites-toolbar-right">
        <span class="tasks-hint">跨站点只读总览 · 新建/编辑请进入站点的「持续监控」</span>
      </div>
```

- [ ] **Step 2: 更新空状态文案** — 把空状态那行（约 36 行）：
```html
      <p style="color:var(--text-tertiary);font-size:13px">{{ schedules.length ? '尝试调整筛选条件' : '点击「新建任务」创建你的第一个定时任务' }}</p>
```
替换为：
```html
      <p style="color:var(--text-tertiary);font-size:13px">{{ schedules.length ? '尝试调整筛选条件' : '在站点详情的「持续监控」里创建定时任务' }}</p>
```

- [ ] **Step 3: 删除整个创建弹窗** — 删除 `<!-- Create Modal -->` 注释 + 其后的整个 `<ModalOverlay :show="showCreateForm" ...> ... </ModalOverlay>`（约 126–261 行，止于 `</ModalOverlay>`）。

- [ ] **Step 4: 精简 import** — 把（约 268 行）：
```js
import { getSchedules, getProfiles, createScheduleApi, pauseScheduleApi, resumeScheduleApi, runNowApi, deleteScheduleApi, getNotifiers } from '../api/index.js';
```
改为：
```js
import { getSchedules, pauseScheduleApi, resumeScheduleApi, runNowApi, deleteScheduleApi } from '../api/index.js';
```
并删除这两行 import（约 270、272 行）：
```js
import { useRoute } from 'vue-router';
```
（⚠ `useRoute` 仍被下方 route watch 使用，**保留** `import { useRoute } from 'vue-router';`。）
```js
import ModalOverlay from '../components/ModalOverlay.vue';
```
（删除 `ModalOverlay` 这一行；`InlineConfirmDelete` 保留。）

- [ ] **Step 5: 删除所有仅服务创建的脚本** — 删除以下声明与函数（它们只被创建弹窗使用，删后无引用）：
  - `showCreateForm`、`createLoading`、`frequencyPreset`、`frequencyOptions`
  - combobox 状态：`profileDropdownOpen`、`freqDropdownOpen`、`modelDropdownOpen`、`profileComboboxRef`、`freqComboboxRef`、`modelComboboxRef`
  - `handleDocClick`、`resetCreateForm`、`createForm`、`notifiers`、`loadNotifiers`
  - `selectedProfileModels`、`frequencyLabel`、`selectCreateProfile`、`selectFrequency`、`modelSearch`、`showAdvanced`、`showAlert`、`filteredTaskModels`、`toggleTaskModel`、`addTaskModel`、`profileMap`、`profiles`
  - `onCreateTask`、`createSchedule`

- [ ] **Step 6: 简化 loadData（去掉 profiles/notifiers 加载）** — 把 `loadData`（约 580–594 行）改为：
```js
async function loadData() {
  loading.value = true;
  try {
    const schedData = await getSchedules();
    schedules.value = schedData.schedules || [];
  } catch (e) {
    toast('加载定时任务失败: ' + e.message, 'error');
  }
  loading.value = false;
}
```

- [ ] **Step 7: 清理生命周期里的 doc-click 监听** — 把（约 602–603 行）：
```js
onMounted(() => { document.addEventListener('mousedown', handleDocClick); });
onUnmounted(() => { store.refreshFn = null; document.removeEventListener('mousedown', handleDocClick); });
```
改为：
```js
onUnmounted(() => { store.refreshFn = null; });
```
并把顶部 `import { ref, computed, watch, onMounted, onUnmounted } from 'vue';` 里不再使用的 `onMounted` 去掉 → `import { ref, computed, watch, onUnmounted } from 'vue';`。

- [ ] **Step 8: 给澄清文案加样式** — 在 `<style scoped>` 里加：
```css
.tasks-hint { font-size: 12px; color: var(--text-tertiary); }
```

- [ ] **Step 9: 构建 + 残留检查** — `cd frontend && bun run build` 必过；再确认无悬空引用：
```bash
grep -nE "showCreateForm|createForm|onCreateTask|createScheduleApi|ModalOverlay|profileMap|filteredTaskModels|handleDocClick" frontend/src/views/TasksView.vue || echo "TasksView 创建相关已清 OK"
```
（预期无输出 → 已清干净。）

- [ ] **Step 10: 提交**
```bash
git add frontend/src/views/TasksView.vue
git commit -m "feat(web): 定时任务页降级为跨站点只读总览，创建统一回持续监控 (#58)"
```

---

## Self-Review
- **Spec 覆盖**：§144 告警就地新建 → Task1（组件 + SiteSchedulesTab create/edit 双接入 + 自动选中最新）；§142 定时任务只读、不在此创建 → Task2（删新建按钮/弹窗/脚本）；§143 文案讲清两者关系 → Task2 Step1/2 文案 + 仍可点站点名跳详情。
- **断链检查**：删 `createScheduleApi`/`getProfiles`/`getNotifiers`/`ModalOverlay` import 后无悬空（Step9 grep 兜底）；`useRoute` 保留（route watch 用）；`InlineConfirmDelete`/`pause/resume/runNow/delete`/`filteredSchedules` 保留。
- **就地新建正确性**：组件校验 name+webhook（对齐 NotifiersManager）；创建后父组件 `loadNotifiers()` + 选 `id` 最大者写入对应表单，create/edit 各自独立（`onNotifierCreated('create'|'edit')`）。
- **占位符**：每步给精确增删/替换代码与命令。
- **测试门槛**：以 `bun run build` 通过为准；视觉确认（持续监控里＋新建渠道→创建后自动选中；定时任务页无新建、文案到位、轻操作仍可用）需人工浏览器；现有 e2e 不直接覆盖创建弹窗（已无），如 `e2e/schedule-crud.spec.js` 走的是 SiteSchedulesTab/接口层不受影响——实现者构建后顺带 `grep -n "新建任务" e2e` 确认无 e2e 依赖该按钮文案（若有则一并提示）。
