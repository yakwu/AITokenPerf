# 中转站完整性诊断（Channel Integrity Diagnostics）

## 背景

AITokenPerf 的目标用户会通过中转站测试 Claude 等模型。当前压测只能证明“这个 API 能返回内容、性能指标是多少”，但不能回答更关键的渠道完整性问题：

- 声称的 `claude-opus` 是否被降级成 `sonnet` 或 `haiku`
- 声称直连 Anthropic 是否实际走了 Bedrock、Vertex 等云厂商路线
- 是否疑似走了非官方/消费端逆向路线，例如 Kiro、Antigravity 类产品代理
- prompt cache 是否真实命中，以及缓存命中对成本和延迟的影响有多大

中转站可以伪造响应元数据，因此本功能不能承诺“证明真实模型身份”。产品定位是黑盒诊断：通过协议行为、能力指纹、错误语义、缓存表现和长期漂移来输出风险等级与证据。

## 目标

- 提供独立的渠道诊断 API 和 UI 入口
- 在压测流程中可选运行轻量诊断，不阻断压测
- 输出结构化诊断报告，而不是单一 `verified=true/false`
- 优先覆盖 Claude 系列中转站，首期重点是缓存、来源路线和明显档位降级
- 记录诊断结果，支持历史查看、趋势对比和异常告警

## 非目标

- 不宣称能 100% 证明真实上游模型
- 首期不承诺区分同家族小版本，例如 `opus-4-6` vs `opus-4-5`
- 不在 UI 中断言“使用了某个具体逆向产品”，只显示“疑似非官方通道风险”
- 不让诊断失败中止压测

## 诊断维度

### 1. 模型档位检测（Model Tier）

目标是识别明显降级风险，例如：

- 期望 `opus`，行为更接近 `sonnet` 或 `haiku`
- 期望 `sonnet`，行为更接近 `haiku`

信号来源：

- 固定私有 probe 集：指令遵循、复杂格式约束、多步推理、长上下文召回
- 官方 Anthropic 基线：同一组 probes 在官方 API 上定期采样，生成 `opus/sonnet/haiku` 行为指纹
- 中转站响应与官方基线的相似度
- 多次采样后的稳定性，避免单次随机输出误判

输出示例：

```json
{
  "expected_tier": "opus",
  "likely_tier": "sonnet",
  "confidence": 0.72,
  "status": "suspected_downgrade",
  "evidence": ["instruction_following_gap", "reasoning_depth_gap"]
}
```

### 2. 上游来源检测（Origin Route）

目标是判断渠道更像哪类上游路线：

- `anthropic_direct`
- `bedrock`
- `vertex`
- `unknown`

信号来源：

- 响应字段、usage 字段、stop reason、错误格式、限流格式
- 非法参数请求的错误语义
- Anthropic 特性支持矩阵，例如 prompt cache 字段、特定 headers、beta feature 行为
- token 计数、最大上下文、流式事件边界表现

注意：中转站可能伪造普通成功响应，因此来源检测必须包含边界请求和错误语义测试。结果只表示“更像某路线”，不是证明。

输出示例：

```json
{
  "likely_origin": "bedrock",
  "confidence": 0.68,
  "status": "route_suspected",
  "evidence": ["bedrock_like_error_shape", "missing_anthropic_cache_usage_fields"]
}
```

### 3. 非官方通道风险（Unofficial Route Risk）

目标是识别疑似消费端逆向或非官方代理路线。产品上不直接断言具体品牌或产品，只输出风险等级。

信号来源：

- 官方 API 特性缺失或行为不一致
- 流式格式不稳定、事件顺序异常、usage 统计缺失
- 错误信息、速率限制、内容过滤语义更像消费端产品
- 多轮上下文污染、隐藏系统提示残留、会话状态串扰
- 长上下文、cache、tool/beta 参数行为异常

输出示例：

```json
{
  "risk": "medium",
  "confidence": 0.61,
  "status": "unofficial_route_suspected",
  "evidence": ["consumer_like_rate_limit", "state_leakage_signal"]
}
```

### 4. 缓存命中率检测（Cache Diagnostics）

这是首期最高优先级模块。它直接影响成本，也比真实模型身份更可量化。

诊断方法：

1. `cold_prefix`：发送长前缀 prompt，建立缓存候选
2. `warm_prefix`：重复相同长前缀，尾部换随机问题，避免完整 response cache 干扰
3. `breaker_prefix`：修改长前缀，使上游 prompt cache 应该失效
4. `repeat_identical`：完全相同请求，用于识别中转站 response cache

判定逻辑：

- 如果 usage 暴露 cache read/write tokens，优先用 usage 计算命中率
- 如果 usage 不暴露缓存字段，用 TTFT、E2E、输入 token 计费差异估算，置信度降低
- 完全相同请求秒回只能证明可能存在 response cache，不能等同于上游 prompt cache
- cache 结果需要区分 `prompt_cache`、`response_cache`、`unknown_cache`

输出示例：

```json
{
  "prompt_cache": {
    "status": "supported",
    "hit_rate": 0.83,
    "evidence": "usage_fields",
    "estimated_cost_saving": 0.42
  },
  "response_cache": {
    "status": "suspected",
    "confidence": 0.74,
    "evidence": ["identical_request_sub_100ms"]
  }
}
```

## 总体状态模型

诊断报告不使用 `verified` 布尔值。每个维度独立输出状态，总体状态只做 UI 汇总。

| 状态 | 含义 |
|------|------|
| `not_run` | 未运行诊断 |
| `unsupported` | 当前模型或协议暂不支持该诊断 |
| `passed` | 未发现明显异常 |
| `warning` | 存在中等风险或证据不足 |
| `critical` | 存在高风险，例如明显降级或缓存声明严重不一致 |
| `inconclusive` | 已运行但无法判断 |
| `error` | 诊断请求失败、超时或权限错误 |

## 覆盖范围

首期覆盖：

- Claude 系列模型：`opus` / `sonnet` / `haiku`
- Anthropic API 兼容接口
- 缓存诊断、来源路线诊断、明显档位降级诊断

后续扩展：

- OpenAI / Gemini / DeepSeek 等厂商
- 更细版本粒度
- 长期漂移检测和自动告警

## 数据模型

当前项目使用 `results` 表保存压测结果。诊断需要同时支持独立运行和压测关联，因此新增独立诊断表，并在 `results` 表保存摘要引用。

### 新增 `channel_diagnostics` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER/SERIAL | 主键 |
| user_id | INTEGER | 用户 ID |
| profile_name | TEXT | 站点名称 |
| model | TEXT | 声称模型 |
| status | TEXT | 总体状态 |
| overall_risk | TEXT | `low` / `medium` / `high` / `unknown` |
| confidence | FLOAT | 总体置信度 0-1 |
| report_json | TEXT/JSONB | 完整诊断报告 |
| created_at | TEXT/TIMESTAMPTZ | 创建时间 |

### 修改 `results` 表

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| channel_diagnostic_id | INTEGER | 0 | 关联的诊断报告 ID |
| channel_diagnostic_status | TEXT | '' | 总体状态摘要 |
| channel_diagnostic_summary_json | TEXT/JSONB | '{}' | UI 所需摘要 |

### 报告结构

```json
{
  "schema_version": 1,
  "profile_name": "Baoyou_Claude",
  "model": "claude-opus-4-6",
  "status": "warning",
  "overall_risk": "medium",
  "confidence": 0.69,
  "dimensions": {
    "model_tier": {
      "status": "suspected_downgrade",
      "expected_tier": "opus",
      "likely_tier": "sonnet",
      "confidence": 0.72,
      "evidence": ["instruction_following_gap"]
    },
    "origin": {
      "status": "route_suspected",
      "likely_origin": "bedrock",
      "confidence": 0.68,
      "evidence": ["bedrock_like_error_shape"]
    },
    "unofficial_route": {
      "status": "inconclusive",
      "risk": "unknown",
      "confidence": 0.35,
      "evidence": []
    },
    "cache": {
      "status": "passed",
      "prompt_cache": {
        "status": "supported",
        "hit_rate": 0.83,
        "estimated_cost_saving": 0.42,
        "evidence": "usage_fields"
      },
      "response_cache": {
        "status": "not_detected",
        "confidence": 0.66
      }
    }
  },
  "probes": [
    {
      "name": "cache_warm_prefix",
      "status": "passed",
      "latency_ms": 820,
      "usage": {
        "input_tokens": 4800,
        "cache_read_input_tokens": 4300
      }
    }
  ]
}
```

## API 设计

### 独立诊断接口

```http
POST /api/channel-diagnostics
```

Body:

```json
{
  "profile_name": "Baoyou_Claude",
  "model": "claude-opus-4-6",
  "modules": ["cache", "origin", "model_tier", "unofficial_route"],
  "mode": "standard"
}
```

Response:

```json
{
  "diagnostic_id": 123,
  "status": "warning",
  "overall_risk": "medium",
  "confidence": 0.69,
  "summary": {
    "model_tier": "suspected_downgrade",
    "origin": "bedrock",
    "unofficial_route": "inconclusive",
    "cache_hit_rate": 0.83
  },
  "report": {}
}
```

约束：

- 用户只能诊断自己拥有的 profile
- `model` 必须属于该 profile 已配置模型，除非用户显式传 `allow_custom_model=true`
- 每次诊断限制最大请求数和最大 token 预算
- 默认 `mode=quick` 只跑缓存和来源轻量 probes；`mode=standard` 再跑模型档位；`mode=deep` 才跑更多行为指纹

### 压测集成

`POST /api/runs` 增加可选字段：

```json
{
  "profile_name": "Baoyou_Claude",
  "models": ["claude-opus-4-6"],
  "enable_channel_diagnostics": true,
  "diagnostic_mode": "quick",
  "diagnostic_modules": ["cache", "origin"]
}
```

流程：

```text
_start_run_for_profile()
  ├─ [可选] 每个模型运行 quick diagnostics
  ├─ 保存 channel_diagnostics 记录
  ├─ 将诊断摘要挂到 BenchTask metadata
  ├─ 执行正常压测流程
  └─ 保存 results 时写入 diagnostic_id/status/summary
```

诊断失败不阻断压测，只在结果中标记 `channel_diagnostic_status=error`。

## 前端展示

### 站点测试页

- 高级参数增加「渠道诊断」开关
- 勾选后显示模块选择：缓存、来源、模型档位、非官方通道风险
- 显示预计额外请求数和 token 成本提示
- 运行中在每个模型卡片显示诊断状态：诊断中、低风险、警告、高风险、无法判断

### 历史结果页

- 模型名称旁显示渠道诊断图标
- hover 显示总体状态、来源判断、缓存命中率、主要风险
- 高风险结果行使用警告色，但不与普通压测失败混淆
- 详情面板展示完整诊断摘要和 probe 证据

### 模型管理页

- Claude 模型增加「诊断」按钮
- 非 Claude 模型首期显示 disabled，并提示暂不支持
- 诊断结果以四个维度卡片展示：模型档位、来源路线、非官方风险、缓存
- 非官方风险只显示风险等级和证据，不显示确定性品牌归因

## 实现文件

### 新增文件

| 文件 | 说明 |
|------|------|
| `app/channel_diagnostics.py` | 诊断核心：probe 定义、运行器、评分与报告生成 |
| `tests/test_channel_diagnostics.py` | 诊断逻辑单元测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `app/db.py` | 新增 `channel_diagnostics` 表，`results` 表增加诊断摘要字段 |
| `app/server.py` | 新增 `/api/channel-diagnostics`，`/api/runs` 集成可选诊断 |
| `app/protocols/anthropic.py` | 保留诊断所需响应元数据、usage cache 字段和错误语义 |
| `frontend/src/api/index.js` | 增加诊断 API client |
| `frontend/src/components/SiteTestTab.vue` | 增加渠道诊断开关和运行态展示 |
| `frontend/src/views/HistoryView.vue` | 结果表和详情展示诊断摘要 |
| `frontend/src/views/ModelsView.vue` | 模型管理页增加独立诊断入口 |

## Probe 策略

Probe 分为公开稳定 probes 和私有行为 probes：

- 公开稳定 probes：缓存、错误语义、协议字段，用于可解释结果
- 私有行为 probes：模型档位和非官方风险，用于降低被中转站针对性适配的概率

所有 probes 必须记录：

- request 类型和模块
- 成功/失败/超时
- 延迟、token usage、cache usage
- 评分证据，不保存过长原始回复

原始回复保存限制：

- 每个 probe 最多保存前 1000 字符
- 默认不保存 API key、headers 中敏感字段
- 轻量结果接口只返回摘要，不返回完整 probe 响应

## 边界情况

- **非 Claude 模型**：返回 `unsupported`，不显示风险判断
- **诊断请求失败**：标记 `error`，不阻断压测
- **probe 超时**：单个 probe 标记 `error` 或 `inconclusive`，不影响其他模块继续运行
- **中转站伪造元数据**：元数据只作为弱信号，不单独决定结论
- **完全相同请求秒回**：优先判断为 response cache 风险，不当作 prompt cache 命中
- **高温度随机输出**：诊断请求固定使用低温度或默认稳定参数，必要时重复采样
- **成本过高**：quick 模式默认只跑低成本 probes；deep 模式需要用户显式选择

## 测试计划

1. `channel_diagnostics` 报告聚合：各模块输出能汇总为正确总体状态
2. 缓存诊断：usage 有 cache 字段时优先用字段计算 hit rate
3. 缓存诊断：usage 无 cache 字段时使用延迟估算，并降低置信度
4. response cache 识别：完全相同请求秒回不误判为 prompt cache
5. 来源路线：Anthropic-like 和 Bedrock-like 错误格式能产生不同 origin 判断
6. 非官方风险：多个弱信号累积为 warning，但不输出确定品牌判断
7. 压测集成：诊断失败不阻断 `/api/runs`
8. 权限校验：用户不能诊断不属于自己的 profile
9. 历史结果：`fields=summary` 不返回完整 probe 响应
10. UI：unsupported / inconclusive / warning / critical 均有明确展示

## MVP 分期

### Phase 1

- `/api/channel-diagnostics`
- cache diagnostics
- origin route 轻量检测
- 结果存储和历史页摘要展示

### Phase 2

- 模型档位行为指纹
- 官方 Anthropic 基线采样
- 标准模式和深度模式

### Phase 3

- 非官方通道风险模型
- 长期漂移监控
- 定时任务异常告警
