# 定时任务多模型测试

## 背景

当前定时任务创建时只能选择一个模型，但后端调度器 `_run_scheduled_task` 实际遍历的是 profile 的全部 `models` 列表，`configs_json.model` 被忽略。用户需要能够手动选择要测试的模型子集。

## 方案

在 `configs_json` 中用 `models` 数组替代 `model` 单值，前端改为多选标签输入，后端优先读取用户选中的模型。

## 数据层

无 DB schema 变更。`configs_json` 是 TEXT 存 JSON，直接改内容：

```json
// 老数据
{ "model": "gpt-4", "concurrency_levels": [10], ... }

// 新数据
{ "models": ["gpt-4", "claude-3.5"], "concurrency_levels": [10], ... }
```

兼容：后端读到 `model` 没有 `models` 时自动包装成单元素数组。

## 后端改动

文件：`app/scheduler.py`，`_run_scheduled_task` 函数，约 line 254-258。

模型提取逻辑改为三级优先链：

```python
# 1. 用户在定时任务中选的模型子集
models = configs_json.get("models") or []
# 2. 老数据兼容：单 model 字段
if not models:
    raw_model = configs_json.get("model") or config.get("model", "")
    models = [raw_model] if raw_model else []
# 3. 兜底：profile 全部模型
if not models:
    models = profile.get("models", [])
```

仅此一处改动，其余调度逻辑不变。

## 前端改动

### 两处表单

1. **TasksView.vue** 模态框（新建定时任务）
2. **SiteSchedulesTab.vue** 创建/编辑表单

核心变化：单选 combobox → 多选标签输入，复用已有的 `.model-tags-input` + `.model-tag` 组件（与站点配置页选模型样式一致）。

### 状态变更

- `createForm.model` / `editForm.model` → `models: []`
- 提交时 `configs_json.models` 发数组

### 表格展示

当前表格"模型"列显示 `configs.model` 单值，改为显示 `configs.models` 数组。多个模型逗号分隔，超过 2 个截断如 `gpt-4, claude-3 +2`。

## 边界与错误处理

- **至少选一个模型**：创建/保存时校验 `models.length > 0`，否则 toast 提示
- **空站点模型**：站点没配置模型时显示 "请先在站点配置中添加模型"
- **手动输入**：保留下拉候选没有时回车手动添加模型 ID 的能力
- **老数据编辑**：编辑已有任务时，`configs_json` 只有 `model` 自动包装成 `[model]`
