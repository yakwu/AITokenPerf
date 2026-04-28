# Claude /v1/messages 缓存诊断设计

## 背景

渠道诊断里的缓存测试需要先收窄到 Claude 系列模型，并且只支持 Anthropic `/v1/messages` 协议。项目中的 Claude 中转站兼容形态也按 `/v1/messages` 处理，不需要覆盖 OpenAI-compatible Chat Completions 或 Responses 协议。

现有实现能解析 Anthropic SSE usage 中的 `cache_read_input_tokens` 和 `cache_creation_input_tokens`，但 probe 请求没有显式设置 `cache_control`，长前缀也不足以稳定达到 Claude prompt cache 的最低缓存长度。因此现有结果容易出现“测试请求本身没有真正请求缓存，却被解释为渠道不支持缓存”的误判。

## 目标

1. Claude 缓存诊断只对 `protocol == "anthropic"` 或自动识别为 Claude 的 `/v1/messages` 请求运行强判定。
2. 使用 Anthropic 官方 prompt caching 机制：在 cacheable content block 上显式添加 `cache_control: {"type": "ephemeral"}`。
3. 以 `usage.cache_creation_input_tokens` 和 `usage.cache_read_input_tokens` 作为 prompt cache 的唯一强证据。
4. 保留 `repeat_identical`，但仅作为 response cache 风险信号，不纳入 prompt cache 命中率。
5. 对无法产生 usage 字段、请求失败、缓存阈值不满足等情况给出明确、可解释的状态。

## 非目标

1. 不支持 OpenAI-compatible 的 Claude 转发格式。
2. 不用 TTFT/E2E 延迟推断 Claude prompt cache 是否命中。
3. 不承诺证明“真实直连 Anthropic”。诊断只说明目标渠道对 Claude `/v1/messages` prompt caching 行为的黑盒证据。
4. 不在本次设计中扩展来源路线、模型档位、能力指纹等其他诊断模块。

## 请求构造

诊断请求使用 Anthropic `/v1/messages` payload：

```json
{
  "model": "claude-...",
  "max_tokens": 100,
  "stream": true,
  "system": [
    {
      "type": "text",
      "text": "<long stable diagnostic prefix>",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [
    { "role": "user", "content": "<probe question>" }
  ],
  "temperature": 0
}
```

长前缀需要显著超过 Claude prompt cache 的最低缓存长度，避免不同 Claude 型号阈值导致误判。实现中应使用确定性文本生成或静态长文本，目标至少 2500 个英文词或等价 token 规模，并在单测中检查长度下限。

`cache_test=True` 继续用于禁止默认 nonce；Claude 诊断还需要额外打开 `cache_control`。普通基准测试是否启用 cache_control 可独立处理，本设计只要求渠道诊断 probe 使用显式 cache breakpoint。

## Probe 流程

### 1. `cold_prefix`

发送长 system block，带 `cache_control`。预期强证据：

- `cache_creation_input_tokens > 0`
- `cache_read_input_tokens == 0` 或很低

如果 cold 请求没有 creation 字段，但后续 warm 有 read 字段，仍可判定 prompt cache 生效；cold creation 缺失只降低解释完整度。

### 2. `warm_prefix x3`

复用完全相同的 system block 和 `cache_control`，只更换 user prompt。预期：

- 至少一个 warm probe 返回 `cache_read_input_tokens > 0`
- 多个 warm probe 命中可提高置信度

命中率只在 warm probe 内计算，不把 cold 或 breaker 纳入分母。

### 3. `breaker_prefix`

改变 cache-controlled system block 的开头或主体内容，仍带 `cache_control`。预期：

- 不应读取旧 prefix cache
- 通常出现新的 `cache_creation_input_tokens > 0`

如果 breaker 返回较高 `cache_read_input_tokens`，标记为 `warning`，原因是旧缓存隔离性或渠道返回 usage 的可信度可疑。

### 4. `repeat_identical`

完全重复 cold 请求，用于识别 response cache 风险。该 probe 的延迟和响应相似度只影响 `response_cache`，不影响 `prompt_cache.hit_rate`。

## 判定模型

### Prompt cache 状态

- `supported`: warm 命中率大于 0，且 breaker 未读取旧缓存。
- `partial`: warm 只有部分命中，breaker 未出现明显异常。
- `warning`: warm 能命中，但 breaker 也读到缓存；或 usage 字段表现自相矛盾。
- `no_usage_fields`: 请求成功但所有 probe 都没有 `cache_creation_input_tokens` / `cache_read_input_tokens`。
- `inconclusive`: 样本不足、关键 probe 失败、或结果无法形成可靠判断。
- `error`: cold 请求失败或协议不支持运行诊断。

### 置信度

- usage 字段齐全且 warm 多次命中：高置信度。
- warm 命中但 cold creation 缺失：中高置信度。
- usage 字段缺失：低置信度，不能判定不支持缓存。
- breaker 异常命中：中等置信度 warning，提示渠道或中转层可能返回了不可解释的缓存数据。

## API 和 UI 表达

API 响应继续返回：

- `prompt_cache.status`
- `prompt_cache.hit_rate`
- `prompt_cache.evidence`
- `prompt_cache.confidence`
- `prompt_cache.samples`
- `response_cache.status`

UI 文案需要避免“缓存正常”这种过度确定表达，建议改为：

- `passed`: `Claude 缓存命中`
- `warning`: `缓存证据异常`
- `no_usage_fields`: `未返回缓存 usage`
- `inconclusive`: `无法判断`
- `error`: `诊断失败`

每个 probe 展示 creation/read token，便于用户直接看到判断依据。

## 测试策略

单元测试需要覆盖：

1. Anthropic 诊断 payload 的 system block 包含 `cache_control: {"type": "ephemeral"}`。
2. Claude 诊断长前缀达到长度下限。
3. cold creation + warm read + breaker creation 被判为 `supported`。
4. warm read 但 breaker 也 read 被判为 `warning`。
5. 所有 usage 字段缺失被判为 `no_usage_fields`，而不是不支持缓存。
6. repeat identical 秒回只影响 `response_cache`，不改变 prompt cache hit rate。
7. 非 Anthropic 协议调用渠道诊断返回明确错误或不支持状态。

## 参考

- Anthropic Prompt caching: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- Anthropic Messages API: https://docs.anthropic.com/en/api/messages
