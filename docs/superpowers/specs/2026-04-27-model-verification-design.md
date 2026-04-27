# 模型身份验证（Model Identity Verification）

## 背景

当前 AITokenPerf 的测试仅覆盖连通性层面（网络、服务器、大模型回复），但无法验证上游渠道返回的是否是声称的模型。例如用户测 claude-opus-4-6，上游可能实际返回 claude-sonnet-4-6 或 claude-opus-4-5，用户无从得知。

## 目标

- 验证 API 返回的模型是否与声称的模型一致
- 集成到压测流程中（可选步骤）
- 提供独立诊断 API 和 UI 入口
- 不匹配时记录并警告（不中止压测）

## 方案

### 验证探测器（Probes）

3 个独立探测器，加权评分：

#### Probe 1 — 自报身份（权重 40%）

- **Prompt**: `"What is your exact model name and version? Reply concosely."`
- **判定**: 回复中是否包含预期模型系列关键词（`opus` / `sonnet` / `haiku`）
- **评分**: 匹配家族 = 100 分，不匹配 = 0 分

#### Probe 2 — 能力边界探测（权重 40%）

利用不同 Claude 模型之间的已知能力差异设计 prompt：

- **Opus vs Sonnet**: 发一个需要极深推理或多步骤规划的问题，观察回答质量和深度
- **Sonnet vs Haiku**: 发一个需要精确指令遵循的复杂 prompt，观察遵循度

每个探测 prompt 有预期行为特征，根据回复特征匹配度评分（0-100）。

#### Probe 3 — 一致性校验（权重 20%）

- 换一种措辞再问一次模型身份
- 对比两次回答是否一致
- 一致 = 100 分，矛盾 = 0 分，部分一致 = 50 分

#### 评分规则

- 总分 = probe1 × 0.4 + probe2 × 0.4 + probe3 × 0.2
- 阈值: >= 70 分为「验证通过」
- 验证未通过时，detected_model 取 probe1 回复中解析出的模型名

### 覆盖范围

首期仅覆盖 Claude 系列（opus / sonnet / haiku）。后续可扩展到 OpenAI 等其他厂商。

## 数据模型

bench_result 表新增字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model_verified | BOOLEAN | NULL | 是否通过验证（NULL = 未验证） |
| detected_model | VARCHAR | NULL | 探测器检测到的模型标识 |
| verification_score | FLOAT | NULL | 加权总分 0-100 |
| verification_details | JSON | NULL | 每个 probe 的详细结果 |

verification_details 结构：
```json
{
  "probes": [
    {
      "name": "self_identify",
      "passed": true,
      "score": 100,
      "response": "I am Claude, specifically the Claude Opus 4 model...",
      "expected_family": "opus"
    },
    {
      "name": "capability_probe",
      "passed": true,
      "score": 80,
      "response": "..."
    },
    {
      "name": "consistency_check",
      "passed": true,
      "score": 75,
      "response": "..."
    }
  ]
}
```

## API 设计

### 独立诊断接口

```
POST /api/verify-model
Body: {
  "profile_id": 1,
  "model": "claude-opus-4-6"
}
Response: {
  "model": "claude-opus-4-6",
  "verified": true,
  "score": 85,
  "detected_model": "claude-opus-4-6",
  "probes": [
    { "name": "self_identify", "passed": true, "score": 100, "response": "..." },
    { "name": "capability_probe", "passed": true, "score": 80, "response": "..." },
    { "name": "consistency_check", "passed": true, "score": 75, "response": "..." }
  ]
}
```

### 集成到压测流程

BenchTask 增加可选的验证步骤：

```
BenchTask.start()
  ├─ [可选] 运行 3 个验证 probes（每个 max_tokens=200，总计约 2-3 秒）
  ├─ 记录验证结果到 task metadata
  ├─ 执行正常压测流程
  └─ 最终结果写入 DB 时带上验证字段
```

验证通过配置项 `enable_verification` 控制是否启用（默认 false）。

## 前端展示

### 压测结果页

- 模型名称旁显示验证状态图标：
  - 绿色勾：验证通过（score >= 70）
  - 黄色警告：验证未通过或检测到不匹配
  - 无图标：未启用验证
- hover 图标显示 tooltip（detected_model、score）
- 验证未通过时该 task 行高亮警告色
- 结果摘要中显示警告信息："检测到模型可能不匹配：声称 claude-opus-4-6，实际可能为 claude-sonnet-4-6"

### 模型管理页

- 每个模型增加「验证」按钮
- 点击调用 `/api/verify-model`
- 展示验证结果详情：声称模型 vs 检测模型、每个 probe 的详细结果和回复内容、总分

## 实现文件

### 新增文件

| 文件 | 说明 |
|------|------|
| `app/verification.py` | 验证核心逻辑：probe 定义、评分、结果解析 |
| `tests/test_verification.py` | 验证逻辑单元测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `app/db.py` | bench_result 表新增 4 个验证字段 |
| `app/client.py` | BenchTask 增加可选验证步骤 |
| `app/server.py` | 新增 `/api/verify-model` 端点 |
| `frontend/src/views/` | 结果页和模型管理页增加验证 UI |

## 边界情况

- **非 Claude 模型**: 跳过验证，model_verified = NULL
- **验证请求失败**: 网络错误等，标记为验证失败但不阻断压测
- **probe 超时**: 单个 probe 超时（10s）视为该 probe 失败，不影响其他 probe
- **模型返回非英文**: 自报身份 probe 的关键词匹配忽略大小写和语言差异
