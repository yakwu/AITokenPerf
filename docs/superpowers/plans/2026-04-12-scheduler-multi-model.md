# 定时任务多模型测试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让定时任务支持多模型测试，用户可从站点模型列表中勾选子集。

**Architecture:** `configs_json` 里用 `models` 数组替代 `model` 单值；前端改为多选标签输入；后端三级优先链读取模型列表。

**Tech Stack:** Python 3 (pytest), Vue 3 (Composition API)

---

### Task 1: 后端 — 写模型提取逻辑的测试

**Files:**
- Create: `tests/test_scheduler_models.py`
- Reference: `app/scheduler.py:254-258`

- [ ] **Step 1: 写失败测试**

```python
"""测试 scheduler 中模型列表提取逻辑（configs_json.models 三级优先链）"""

import pytest


def _extract_models(configs_json: dict, config: dict, profile: dict) -> list[str]:
    """从 scheduler.py 提取出的模型提取函数，用于独立测试。
    优先级：configs_json.models → configs_json.model / config.model → profile.models
    """
    models = configs_json.get("models") or []
    if not models:
        raw_model = configs_json.get("model") or config.get("model", "")
        models = [raw_model] if raw_model else []
    if not models:
        models = profile.get("models", [])
    return models


def test_configs_json_models_takes_priority():
    """configs_json.models 最优先"""
    result = _extract_models(
        configs_json={"models": ["gpt-4", "claude-3"]},
        config={"model": "fallback"},
        profile={"models": ["a", "b", "c"]},
    )
    assert result == ["gpt-4", "claude-3"]


def test_fallback_to_configs_json_model():
    """老数据兼容：configs_json.model 单值"""
    result = _extract_models(
        configs_json={"model": "gpt-4"},
        config={"model": "other"},
        profile={"models": ["a", "b"]},
    )
    assert result == ["gpt-4"]


def test_fallback_to_config_model():
    """configs_json 里没有模型，用 config.model"""
    result = _extract_models(
        configs_json={},
        config={"model": "deepseek-v3"},
        profile={"models": ["a", "b"]},
    )
    assert result == ["deepseek-v3"]


def test_fallback_to_profile_models():
    """都没有，用 profile 全部模型"""
    result = _extract_models(
        configs_json={},
        config={},
        profile={"models": ["gpt-4", "claude-3", "gemini-pro"]},
    )
    assert result == ["gpt-4", "claude-3", "gemini-pro"]


def test_empty_everything():
    """全部为空返回空列表"""
    result = _extract_models(configs_json={}, config={}, profile={})
    assert result == []


def test_configs_json_models_empty_array():
    """configs_json.models 是空数组时 fall through"""
    result = _extract_models(
        configs_json={"models": []},
        config={"model": "fallback"},
        profile={"models": ["a"]},
    )
    assert result == ["fallback"]


def test_configs_json_model_empty_string():
    """configs_json.model 是空字符串时 fall through"""
    result = _extract_models(
        configs_json={"model": ""},
        config={"model": "deepseek"},
        profile={"models": ["a"]},
    )
    assert result == ["deepseek"]
```

- [ ] **Step 2: 运行测试确认全部通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_scheduler_models.py -v`
Expected: 7 passed（纯逻辑函数，直接通过）

- [ ] **Step 3: Commit**

```bash
git add tests/test_scheduler_models.py
git commit -m "test: 定时任务多模型提取逻辑测试"
```

---

### Task 2: 后端 — 改 scheduler.py 模型提取

**Files:**
- Modify: `app/scheduler.py:254-258`

- [ ] **Step 1: 替换模型提取逻辑**

将 `app/scheduler.py` 第 254-258 行：

```python
        # 获取模型列表（支持多模型 Profile）
        models = profile.get("models", [])
        if not models:
            raw_model = config.get("model", "")
            models = [raw_model] if raw_model else []
```

替换为：

```python
        # 获取模型列表（优先用定时任务中选的模型子集）
        models = configs_json.get("models") or []
        if not models:
            raw_model = configs_json.get("model") or config.get("model", "")
            models = [raw_model] if raw_model else []
        if not models:
            models = profile.get("models", [])
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_scheduler_models.py -v`
Expected: 7 passed

- [ ] **Step 3: Commit**

```bash
git add app/scheduler.py
git commit -m "feat: 调度器支持 configs_json.models 多模型优先链"
```

---

### Task 3: 前端 — SiteSchedulesTab 创建表单改多选

**Files:**
- Modify: `frontend/src/components/SiteSchedulesTab.vue`

**改 state：**

将 `defaultCreateForm` 函数（约 line 232-238）：

```javascript
function defaultCreateForm() {
  return {
    name: '',
    schedule_value: 300,
    model: profileModels.value[0] || '',
  };
}
```

改为：

```javascript
function defaultCreateForm() {
  return {
    name: '',
    schedule_value: 300,
    models: [],
  };
}
```

将 `editForm` 初始值（约 line 261-266）：

```javascript
const editForm = ref({
  id: null,
  name: '',
  schedule_value: 300,
  model: '',
});
```

改为：

```javascript
const editForm = ref({
  id: null,
  name: '',
  schedule_value: 300,
  models: [],
});
```

**改模板 — 创建表单模型选择**（约 line 39-45）：

将：

```html
          <div class="form-group">
            <label class="form-label">选择模型</label>
            <select class="form-input" v-model="createForm.model">
              <option v-for="m in profileModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <div class="form-hint" v-if="!profileModels.length">站点未配置模型，请先在配置 Tab 中添加</div>
          </div>
```

改为：

```html
          <div class="form-group">
            <label class="form-label">选择模型</label>
            <div class="combobox" ref="createModelComboboxRef">
              <div class="model-tags-input" @click="createModelDropdownOpen = true">
                <span v-for="(m, i) in createForm.models" :key="m" class="model-tag">
                  {{ m }}
                  <button type="button" class="model-tag-remove" @click.stop="createForm.models.splice(i, 1)">&times;</button>
                </span>
                <input class="model-tag-search" v-model="createModelSearch" :placeholder="createForm.models.length ? '' : '选择或搜索模型'" @focus="createModelDropdownOpen = true" @keydown.enter.prevent="addCreateModel()" @keydown.backspace="createForm.models.length && !createModelSearch && createForm.models.pop()" @keydown.escape="createModelDropdownOpen = false" autocomplete="off">
              </div>
              <button class="combobox-toggle" type="button" @click.stop="createModelDropdownOpen = !createModelDropdownOpen" @mousedown.prevent>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
              </button>
              <div class="combobox-dropdown" v-show="createModelDropdownOpen">
                <div v-for="m in filteredCreateModels" :key="m" class="combobox-option" :class="{ active: createForm.models.includes(m) }" @mousedown.prevent="toggleCreateModel(m)">{{ m }}</div>
                <div class="combobox-empty" v-show="!filteredCreateModels.length && createModelSearch">无匹配，按回车添加「{{ createModelSearch }}」</div>
                <div class="combobox-empty" v-show="!filteredCreateModels.length && !createModelSearch">暂无模型</div>
              </div>
            </div>
            <div class="form-hint" v-if="!profileModels.length">站点未配置模型，请先在配置 Tab 中添加</div>
          </div>
```

**改模板 — 编辑表单模型选择**（约 line 167-170 区域）：

将编辑表单里的 `<select class="form-input" v-model="editForm.model">` 整个 select 替换为同样的多选标签输入（数据绑定为 `editForm.models`、`editModelSearch`、`editModelDropdownOpen` 等，逻辑同上但变量名加 `edit` 前缀）。

**改 script — 添加新状态和方法：**

在 `// ---- Create form ----` 区域后面添加：

```javascript
// Multi-model select state (create)
const createModelDropdownOpen = ref(false);
const createModelSearch = ref('');
const createModelComboboxRef = ref(null);

const filteredCreateModels = computed(() => {
  const q = (createModelSearch.value || '').toLowerCase();
  const list = profileModels.value.filter(m => !createForm.value.models.includes(m));
  if (!q) return list;
  return list.filter(m => m.toLowerCase().includes(q));
});

function toggleCreateModel(m) {
  const idx = createForm.value.models.indexOf(m);
  if (idx >= 0) createForm.value.models.splice(idx, 1);
  else createForm.value.models.push(m);
  createModelSearch.value = '';
}

function addCreateModel() {
  if (!createModelSearch.value.trim()) return;
  const n = createModelSearch.value.trim();
  if (!createForm.value.models.includes(n)) createForm.value.models.push(n);
  createModelSearch.value = '';
}

// Multi-model select state (edit)
const editModelDropdownOpen = ref(false);
const editModelSearch = ref('');
const editModelComboboxRef = ref(null);

const filteredEditModels = computed(() => {
  const q = (editModelSearch.value || '').toLowerCase();
  const list = profileModels.value.filter(m => !editForm.value.models.includes(m));
  if (!q) return list;
  return list.filter(m => m.toLowerCase().includes(q));
});

function toggleEditModel(m) {
  const idx = editForm.value.models.indexOf(m);
  if (idx >= 0) editForm.value.models.splice(idx, 1);
  else editForm.value.models.push(m);
  editModelSearch.value = '';
}

function addEditModel() {
  if (!editModelSearch.value.trim()) return;
  const n = editModelSearch.value.trim();
  if (!editForm.value.models.includes(n)) editForm.value.models.push(n);
  editModelSearch.value = '';
}
```

**改 `createSchedule` 函数**（约 line 353-389）：

将校验 `if (!f.model)` 改为 `if (!f.models.length)`，toast 改为 `'请至少选择一个模型'`。

将 `configs_json` 里的 `model: f.model` 改为 `models: f.models`。

**改 `saveEdit` 函数**（约 line 396-428）：

将 `configs.model = f.model` 改为 `configs.models = f.models`。

**改 `startEdit` 函数**（约 line 276-289）：

将 `model: configs.model || ''` 改为 `models: configs.models || (configs.model ? [configs.model] : [])`（兼容老数据）。

**改 `getModelFromSchedule` 函数**（约 line 323-326）：

```javascript
function getModelFromSchedule(s) {
  const configs = s.configs_json || s.configs || {};
  const models = configs.models || (configs.model ? [configs.model] : []);
  if (!models.length) return '-';
  if (models.length <= 2) return models.join(', ');
  return models.slice(0, 2).join(', ') + ' +' + (models.length - 2);
}
```

**改 click-outside 处理：** 添加 `createModelComboboxRef` 和 `editModelComboboxRef` 的 click-outside 逻辑（在 `onMounted`/`onUnmounted` 中与其他 listener 一起管理）。

- [ ] **Step 1: 改 state 和模板**
- [ ] **Step 2: 改 script 逻辑**
- [ ] **Step 3: 构建验证**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && bun run build 2>&1 | tail -3`
Expected: `✓ built in ...`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SiteSchedulesTab.vue
git commit -m "feat: SiteSchedulesTab 创建/编辑表单支持多模型选择"
```

---

### Task 4: 前端 — TasksView 创建表单改多选

**Files:**
- Modify: `frontend/src/views/TasksView.vue`

**改 state：** `createForm` 里 `model: ''` → `models: []`

将 `resetCreateForm` 里的赋值对应改掉。

**改模板 — Model Combobox 替换为多选标签输入**（约 line 169-185 区域）：

将单选 combobox 替换为多选 model-tags-input（绑定 `createForm.models`，逻辑与 SiteSchedulesTab 同构）。

**改 script：**

添加 `modelSearch` ref、`filteredModels` computed（过滤掉已选的）、`addModel`/`removeModel`/`toggleModel` 方法。

将 `selectCreateModel(m)` 改为 toggle 逻辑（已选则移除，未选则添加）。

**改 `createSchedule` 函数**（约 line 393-434）：

将校验 `if (!f.model)` 改为 `if (!f.models.length)`，toast 改为 `'请至少选择一个模型'`。

将 `configs_json` 里的 `model: f.model` 改为 `models: f.models`。

**改 `getModelFromSchedule` 和 `getSiteName` 相关：** `getModelFromSchedule` 改为支持 `models` 数组（同 Task 3 的逻辑）。

- [ ] **Step 1: 改 state 和模板**
- [ ] **Step 2: 改 script 逻辑**
- [ ] **Step 3: 构建验证**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && bun run build 2>&1 | tail -3`
Expected: `✓ built in ...`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/TasksView.vue
git commit -m "feat: TasksView 新建定时任务支持多模型选择"
```

---

### Task 5: 验收 — 端到端验证

- [ ] **Step 1: 运行全部后端测试**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_scheduler_models.py -v`
Expected: 7 passed

- [ ] **Step 2: 前端构建**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && bun run build`
Expected: 构建成功无错误

- [ ] **Step 3: Commit（如有遗漏修复）**
