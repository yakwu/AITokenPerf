# 模型管理整改设计文档

## 背景

当前模型管理存在以下问题：

1. **厂商列表硬编码三份** — `SitesView.vue`、`SiteConfigTab.vue`、`pricing.py` 各维护一份 `providerOptions` / `PROVIDER_MODEL_KEYWORDS`，容易不同步
2. **厂商→模型映射靠关键词猜** — `pricing.py` 用 `PROVIDER_MODEL_KEYWORDS` 按模型名关键词匹配，逻辑脆弱
3. **Combobox 组件手写了三遍** — 每个页面都手搓一套 combobox + click-outside + dropdown，bug 修了一处另一处还在
4. **模型数据源混乱** — LiteLLM 几千个模型 + 实时 API 双源合并，用户实际只需几十个主流模型
5. **站点"厂商"字段语义模糊** — 混淆了"模型厂商"和"服务提供商"两个概念

## 设计目标

- 自维护主流模型列表（JSON 配置文件），按模型厂商分类
- 站点不绑定厂商，模型选择时通过厂商 chips 本地过滤
- 模型管理页双 Tab：「我的模型」管理精选列表，「模型库」浏览 LiteLLM 全量数据
- LiteLLM 退化为纯价格查询服务 + 模型库浏览
- 提取通用组件，消除重复代码

## 一、数据模型

### 1.1 `data/builtin_models.json`

新增 JSON 配置文件作为"我的模型"的权威数据源：

```json
{
  "vendors": [
    { "id": "anthropic", "name": "Anthropic", "label": "Anthropic (Claude)" },
    { "id": "openai", "name": "OpenAI", "label": "OpenAI" },
    { "id": "deepseek", "name": "DeepSeek", "label": "DeepSeek" },
    { "id": "qwen", "name": "Qwen", "label": "Qwen (通义千问)" },
    { "id": "google", "name": "Google", "label": "Google (Gemini)" },
    { "id": "mistral", "name": "Mistral", "label": "Mistral" },
    { "id": "cohere", "name": "Cohere", "label": "Cohere" },
    { "id": "bytedance", "name": "ByteDance", "label": "字节 (豆包)" },
    { "id": "zhipu", "name": "Zhipu", "label": "智谱 (GLM)" },
    { "id": "moonshot", "name": "Moonshot", "label": "Moonshot (Kimi)" }
  ],
  "models": [
    { "id": "claude-opus-4-20250514", "vendor": "anthropic", "enabled": true },
    { "id": "claude-sonnet-4-20250514", "vendor": "anthropic", "enabled": true },
    { "id": "claude-haiku-4-20250514", "vendor": "anthropic", "enabled": true },
    { "id": "gpt-4o", "vendor": "openai", "enabled": true },
    { "id": "gpt-4o-mini", "vendor": "openai", "enabled": true },
    { "id": "o3", "vendor": "openai", "enabled": true },
    { "id": "o4-mini", "vendor": "openai", "enabled": true },
    { "id": "deepseek-chat", "vendor": "deepseek", "enabled": true },
    { "id": "deepseek-reasoner", "vendor": "deepseek", "enabled": true }
  ]
}
```

- `vendors` — 厂商注册表，前端后端共用唯一来源
- `models[].vendor` — 指向 `vendors[].id`，硬绑定
- `models[].enabled` — 是否在站点新建时展示给用户
- 用户添加自定义模型时追加 `{ id, vendor, enabled, custom: true }`

### 1.2 三层数据职责

| 层 | 职责 | 数据源 |
|---|---|---|
| **内置列表** | "推荐你测哪些模型" | `data/builtin_models.json` |
| **用户输入** | "我还想测这个" | 手动输入任意模型 ID |
| **LiteLLM** | "这个模型多少钱" + 模型库浏览 | 远程价格库（自动更新） |

用户手动输入的模型 ID，LiteLLM 仍然可以通过模糊/前缀匹配计算价格。

### 1.3 现有 `data/models_config.json` 的迁移

现有的 `models_config.json`（仅含 `enabled_models` 扁平列表）将被 `builtin_models.json` 替代。迁移策略：
- 如果 `models_config.json` 存在且有 `enabled_models`，启动时读取并合并到新 JSON 的 enabled 状态
- 迁移完成后可以删除旧文件

## 二、后端 API

### 2.1 现有 API 调整

| API | 改动 |
|---|---|
| `GET /api/pricing/models` | 从 `builtin_models.json` 读取。参数 `vendor` 替代 `provider`，`enabled_only` 保留 |
| `PUT /api/pricing/models-config` | 改为直接修改 `builtin_models.json`（增删改模型、切换 enabled） |
| `GET /api/pricing/models-config` | 返回完整 `builtin_models.json` 内容 |

### 2.2 新增 API

| API | 用途 |
|---|---|
| `GET /api/pricing/library` | 返回 LiteLLM 全量模型列表，用于"模型库"Tab。支持 `vendor`、`search`、`page`、`page_size` 参数 |
| `GET /api/pricing/vendors` | 返回 vendors 列表，前端所有厂商相关 UI 统一从这里取 |

### 2.3 `pricing.py` 职责

```python
class PricingService:
    # LiteLLM 相关（保留）
    async def start()                    # 加载价格缓存
    async def refresh()                  # 刷新价格数据
    def get_pricing(model_id) -> dict    # 按模型名查价格（精确/前缀匹配）
    def get_library(vendor?, search?, page?, page_size?) -> list  # 浏览 LiteLLM 全量

    # 内置模型相关（新增/改造）
    def get_vendors() -> list            # 从 JSON 读厂商列表
    def get_builtin_models(vendor?, enabled_only?) -> list  # 从 JSON 读模型列表
    def save_builtin_models(data)        # 写 JSON（增删改模型、切换 enabled）
```

去掉 `PROVIDER_MODEL_KEYWORDS` 关键词映射逻辑，厂商归属由 JSON 中 `vendor` 字段直接确定。

### 2.4 站点 profile 的 provider 字段

- 保留字段，不删除，向后兼容
- 语义改为可选的"服务提供商"备注，不参与模型过滤
- `detect_protocol()` 已经能根据模型名自动判断协议，有 provider 参考，没有也能工作

## 三、前端组件

### 3.1 新增 `ModelSelector.vue`

通用模型选择器组件，替代三处手写的 combobox：

```vue
<ModelSelector
  v-model="form.models"
  :vendor-filter="true"
  :allow-custom="true"
  placeholder="搜索或选择模型"
/>
```

内部结构：

```
┌───────────────────────────────────────────────┐
│ [全部] [Anthropic] [OpenAI] [DeepSeek] ...    │  ← 厂商过滤 chips
├───────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────┐ │
│ │ [claude-sonnet-4 ×] [gpt-4o ×]           │ │  ← 已选标签
│ │ 搜索模型...                          ▼    │ │  ← 搜索输入
│ ├───────────────────────────────────────────┤ │
│ │ claude-opus-4                             │ │  ← 过滤后的候选列表
│ │ claude-haiku-4                            │ │
│ │ 无匹配，按回车添加「xxx」                  │ │
│ └───────────────────────────────────────────┘ │
└───────────────────────────────────────────────┘
```

关键设计：
- **组件挂载时**一次性调用 `/api/pricing/models?enabled_only=true` 加载全部已启用模型
- **厂商 chips** 做纯本地过滤，不再每次切厂商都请求 API
- **样式沿用现有 combobox 风格**（`.combobox`、`.combobox-dropdown`、`.combobox-option`、`.model-tags-input`、`.model-tag` 等现有 CSS class）
- **click-outside** 逻辑只写一次，在组件内部处理

### 3.2 新增 `VendorCombobox.vue`

通用厂商选择器，模型管理页的厂商筛选用：

```vue
<VendorCombobox v-model="filterVendor" :show-all="true" />
```

- 数据从 `/api/pricing/vendors` 获取
- 沿用现有 combobox 样式

### 3.3 页面改造

**SitesView.vue（新建站点弹窗）：**
- 去掉独立的"模型厂商" combobox
- 模型选择改用 `<ModelSelector>`
- 字段简化为：站点名称、目标地址、API Key、模型

**SiteConfigTab.vue（站点编辑）：**
- 同上，去掉 Provider combobox，模型选择改用 `<ModelSelector>`

**ModelsView.vue（模型管理页）：**
- 改为双 Tab 结构：
  - **Tab 1「我的模型」**：管理 `builtin_models.json`，表格列：启用 checkbox | 模型名 | 厂商 | 价格（LiteLLM 查）| 操作
  - **Tab 2「模型库」**：浏览 LiteLLM 全量数据，表格列：模型名 | 厂商 | 输入价格 | 输出价格 | max tokens | 「添加」按钮
- Tab 样式沿用 `SiteDetailView.vue` 的 `.tab-nav`

### 3.4 删除的代码

- `SitesView.vue` 中手写的 provider combobox + model combobox 逻辑（~100 行）
- `SiteConfigTab.vue` 中手写的 provider combobox + model combobox 逻辑（~120 行）
- `SitesView.vue` / `SiteConfigTab.vue` 中硬编码的 `providerOptions` 数组
- `pricing.py` 中的 `PROVIDER_MODEL_KEYWORDS` 字典

## 四、样式约束

所有新组件必须沿用现有设计系统：
- combobox 结构：`.combobox` > `.form-input` + `.combobox-toggle` + `.combobox-dropdown` > `.combobox-option`
- tag 样式：`.model-tags-input` > `.model-tag` > `.model-tag-remove`
- 按钮：`.btn .btn-primary`、`.btn .btn-ghost`、`.btn-sm`
- 过滤 chips：`.filter-chips` > `.filter-chip`
- 表格：复用现有 `.models-table` 样式
- Tab：复用 `SiteDetailView.vue` 的 `.tab-nav` + `.tab-btn`

不引入新的 UI 框架或组件库。

## 五、测试计划

1. **模型管理页「我的模型」Tab**：启用/禁用模型 → 保存 → 刷新后状态保持
2. **模型管理页「模型库」Tab**：浏览 LiteLLM 数据 → 按厂商过滤 → 搜索 → 添加到我的模型
3. **新建站点**：厂商 chips 过滤 → 选择模型 → 手动输入自定义模型 → 创建成功
4. **站点编辑**：加载已有模型 → 修改 → 保存 → 刷新后状态保持
5. **价格查询**：内置模型显示价格 → 自定义模型 LiteLLM 匹配显示价格 → 未知模型显示"-"
6. **向后兼容**：已有站点的 provider 字段不影响功能

## 六、不做的事

- 不引入新的 UI 组件库
- 不改数据库 schema
- 不删除 profile 表的 provider 字段
- 不做模型版本管理
- 不做用户级模型列表隔离（所有用户共享同一份 builtin_models.json）
