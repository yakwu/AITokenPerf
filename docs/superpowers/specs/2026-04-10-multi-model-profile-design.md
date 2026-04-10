# 多模型 Profile 设计文档

## 背景

当前每个 Profile 只能绑定一个模型（`model` 字段为单个字符串）。用户希望在一个 Profile（同一个 url+key）中配置多个模型，每次测试自动对所有模型发送请求，便于对比同一渠道下不同模型的质量。

## 方案

**方案 A：数据库层 model 字段改为 JSON 数组**

Profile 的 `model` 字段从 `TEXT`（单字符串）改为存储 JSON 数组字符串。调度层在最外层展开为多个 BenchTask，每个 task 的 config.model 仍然是单个字符串，底层代码完全不需要改。

## 一、数据模型变更

### 数据库存储

`profiles.model` 字段存储格式变更：

```
旧: "claude-opus-4-6"
新: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]
```

### 迁移策略

- 启动时/读取时做兼容处理：检测到旧的纯字符串格式自动包装为单元素数组
- 不需要专门的迁移脚本
- 写入时统一存数组格式

### API 变更

| 接口 | 变更 |
|------|------|
| `POST /api/profiles` | `model` 字段从 string 变为 `list[str]` |
| `GET /api/profiles` | 返回 `models: [...]`（字段名改为复数） |
| `PUT /api/profiles/{id}` | `models: [...]` |
| `GET /api/profiles/active` | 返回 `models: [...]` |

## 二、调度层展开逻辑

核心原则：**调度层把多模型 Profile 展开为多个独立 BenchTask，每个 task 的 config.model 仍是单个字符串。**

### 手动测试 (`start_bench`)

```python
active = await get_active_profile(user_id)  # models: ["m1", "m2", "m3"]
models = active.get("models", [])
for model_name in models:
    task_config = dict(config)
    task_config["model"] = model_name
    task_config["protocol"] = detect_protocol(model_name, provider)
    bt = BenchTask(...)
    tasks.append(bt)
```

### 定时任务 (`scheduler._run_scheduled_task`)

- 遍历每个 profile 的 models 列表
- 每个 model 生成一个独立的 BenchTask
- 定时任务名称自动追加模型后缀

### `start_multi_model_bench` 接口

可简化或废弃，因为 `start_bench` 本身就支持多模型了。

### 结果关联

- 每条测试结果的 `config_json.model` 仍是单个字符串
- 历史记录、仪表盘筛选逻辑不需要改

## 三、前端变更

### ProfileView.vue（配置管理页）

- model 输入从单个 combobox 改为 **tag 多选组件**
- 用户可以从下拉列表选择模型（数据来自 `/api/pricing/models`）
- 支持手动输入自定义模型 ID
- 已选模型以 tag/chip 形式展示，可逐个删除
- 新建 Profile 时默认选中一个模型

### TestView.vue（测试页）

- 选中 Profile 后展示 "模型: opus-4.6, sonnet-4.6, haiku-4.5"（逗号分隔）
- 点击"开始测试"时自动为每个模型创建独立任务
- 多任务进度条区域已支持多 task 并行，无需大改

### HistoryView.vue / DashboardView.vue

- 不需要改动，`r.config?.model` 仍是单个字符串

## 四、改动范围

### 需要改的文件

| 文件 | 改动 |
|------|------|
| `app/db.py` | Profile CRUD — model 读写改为 JSON 数组，读取时兼容旧格式 |
| `app/server.py` | `start_bench` 遍历 models 展开任务；Profile API 改为 models |
| `app/scheduler.py` | `_run_scheduled_task` 遍历 profile.models 展开任务 |
| `frontend/src/views/ProfileView.vue` | model 输入改为 tag 多选 |
| `frontend/src/views/TestView.vue` | 展示多模型信息 |

### 不需要改的文件

| 文件 | 原因 |
|------|------|
| `app/client.py` | 每个 task 的 config.model 仍是单字符串 |
| `app/protocols/*` | 不受影响 |
| `app/stats.py` | 结果构建逻辑不变 |
| `frontend/src/views/DashboardView.vue` | model 筛选逻辑不变 |
| `frontend/src/views/HistoryView.vue` | model 展示/筛选逻辑不变 |
