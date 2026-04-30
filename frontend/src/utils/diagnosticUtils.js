/**
 * 诊断结果展示工具函数
 */

// ---- Status helpers ----
export function diagStatusColor(status) {
  const map = {
    passed: 'var(--success)',
    warning: 'var(--warning)',
    failed: 'var(--danger)',
    error: 'var(--danger)',
    pending: 'var(--text-tertiary)',
    running: 'var(--accent)',
  }
  return map[status] || 'var(--text-tertiary)'
}

export function diagStatusLabel(status) {
  const map = {
    passed: '通过',
    warning: '存疑',
    failed: '失败',
    error: '出错',
    pending: '等待中',
    running: '运行中',
  }
  return map[status] || status
}

export function diagStatusTooltip(status) {
  const map = {
    passed: '所有探针均通过',
    warning: '部分探针存在可疑结果',
    failed: '存在探针失败',
    error: '诊断过程出错',
  }
  return map[status] || ''
}

// ---- Probe display helpers ----
export function diagProbeLabel(name) {
  const map = {
    cold_prefix: '冷前缀',
    warm_prefix: '热前缀',
    breaker_prefix: '断路前缀',
    repeat_identical: '重复请求',
  }
  return map[name] || name
}

export function probeTokenColor(type) {
  const map = {
    cache_creation: 'var(--accent)',
    cache_read: 'var(--success)',
    input: 'var(--text-secondary)',
    output: 'var(--text-primary)',
  }
  return map[type] || 'var(--text-tertiary)'
}

export function probeTokenCheck(type) {
  const map = {
    cache_creation: '创建',
    cache_read: '读取',
    input: '输入',
    output: '输出',
  }
  return map[type] || type
}

// ---- Category helpers ----
export function categoryLabel(catId) {
  const map = {
    connectivity: '连通性',
    streaming: '流式传输',
    context: '多轮上下文',
    tool_use: '工具调用',
    structured: '结构化输出',
    cache: 'Prompt Cache',
  }
  return map[catId] || catId
}

export function probeDisplayName(name) {
  const map = {
    single_non_stream: '单轮非流式',
    stream_long_output: '流式长输出',
    round_1: '第1轮',
    round_2: '第2轮',
    round_3: '第3轮',
    round_4: '第4轮',
    round_5: '第5轮',
    round_6: '第6轮',
    tool_call_round1: '工具调用-请求',
    tool_call_round2: '工具调用-结果',
    structured_json: '结构化 JSON',
    cold_prefix: '首次请求',
    warm_prefix: '再次请求',
    breaker_prefix: '不同内容',
    repeat_identical: '重发首次',
  }
  return map[name] || name
}

export function categoryStatusColor(status) {
  const map = {
    passed: 'var(--success)',
    warning: 'var(--warning)',
    failed: 'var(--danger)',
    error: 'var(--danger)',
  }
  return map[status] || 'var(--text-tertiary)'
}
