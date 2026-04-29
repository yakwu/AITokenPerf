/** 诊断状态颜色/文案映射 — 共享工具函数 */

export function diagStatusColor(status) {
  const map = { passed: 'var(--success)', warning: 'var(--warning)', critical: 'var(--danger)', inconclusive: 'var(--text-tertiary)', no_usage_fields: 'var(--info)', no_cache: 'var(--warning)', error: 'var(--danger)' };
  return map[status] || 'var(--text-tertiary)';
}

export function diagStatusLabel(status) {
  const map = { passed: '缓存生效', warning: '结果存疑', critical: '高风险', inconclusive: '无法判断', no_usage_fields: '渠道未反馈缓存信息', no_cache: '未达到缓存阈值', error: '诊断失败' };
  return map[status] || status;
}

export function diagStatusTooltip(status) {
  const map = {
    passed: '首次请求建立了缓存，后续请求命中缓存，且不同内容的请求没有误读旧缓存 — 说明缓存机制正常',
    warning: '相同内容能命中缓存，但不同内容的请求也读到了缓存 — 可能是渠道在中间层做了缓存，而非 Claude 真实缓存',
    no_usage_fields: '请求成功了，但渠道没有返回缓存相关信息，无法判断缓存是否生效',
    no_cache: '渠道返回了缓存相关字段，但值全是 0 — 可能是发送的内容没达到缓存最低长度要求，或者渠道本身不支持缓存',
    inconclusive: '部分请求失败或超时，无法得出可靠结论',
    error: '请求没有成功，可能是配置错误或渠道不可用',
    critical: '检测到严重问题',
  };
  return map[status] || '';
}

export function diagProbeLabel(name) {
  const map = {
    cold_prefix: '首次请求',
    warm_prefix: '再次请求',
    breaker_prefix: '不同内容',
    repeat_identical: '重发首次',
  };
  return map[name] || name;
}

export function probeTokenColor(probeName, tokenType) {
  const expectRead = ['warm_prefix', 'repeat_identical'].includes(probeName);
  if (tokenType === 'read' || tokenType === 'mixed') {
    return expectRead ? 'var(--success)' : 'var(--danger)';
  }
  if (tokenType === 'creation') {
    return 'var(--info)';
  }
  return expectRead ? 'var(--warning)' : 'var(--text-tertiary)';
}

export function probeTokenCheck(probe) {
  if (!probe.expected_total_tokens || probe.expected_total_tokens <= 0) return null;
  const u = probe.usage || {};
  const cacheable = (u.cache_creation_input_tokens || 0) + (u.cache_read_input_tokens || 0);
  const total = (u.input_tokens || 0) + cacheable;
  if (cacheable > 0 && probe.expected_system_tokens > 0 && cacheable > probe.expected_system_tokens * 1.5) {
    const pct = ((cacheable - probe.expected_system_tokens) / probe.expected_system_tokens * 100).toFixed(0);
    return { text: `计费多 ${pct}%`, color: 'var(--danger)', tip: `缓存区计费 ${cacheable} tokens，但我们发的内容预估只有 ${probe.expected_system_tokens} tokens — 渠道可能在你的内容里注入了额外东西，多出来的部分你也在买单` };
  }
  if (total > 0 && total > probe.expected_total_tokens * 2) {
    const pct = ((total - probe.expected_total_tokens) / probe.expected_total_tokens * 100).toFixed(0);
    return { text: `计费多 ${pct}%`, color: 'var(--danger)', tip: `渠道计费 ${total} tokens，但我们只发了 ${probe.expected_total_tokens} tokens 的内容 — 多出来的 ${total - probe.expected_total_tokens} tokens 可能是渠道注入的` };
  }
  if (total > 0 && total < probe.expected_total_tokens * 0.3) {
    const pct = ((probe.expected_total_tokens - total) / probe.expected_total_tokens * 100).toFixed(0);
    return { text: `计费少 ${pct}%`, color: 'var(--warning)', tip: `渠道计费 ${total} tokens，但我们发了 ${probe.expected_total_tokens} tokens — 渠道可能没有把你发的内容全部传给 Claude` };
  }
  return null;
}
