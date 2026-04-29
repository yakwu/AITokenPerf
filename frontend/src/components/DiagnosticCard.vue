<template>
  <div class="diag-result-card" :class="{ 'diag-pending': status === 'pending' }">
    <!-- Status Badge -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span :style="'background:' + diagStatusColor(status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
        {{ diagStatusLabel(status) }}
      </span>
      <span v-if="diagStatusTooltip(status)" class="info-tip" :data-tip="diagStatusTooltip(status)">?</span>
    </div>

    <!-- Cache Hit Rate + Confidence -->
    <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary);margin-bottom:8px">
      <span v-if="hitRate != null">命中率: <strong>{{ (hitRate * 100).toFixed(1) }}%</strong></span>
      <span v-if="confidence != null">置信度: <strong>{{ (confidence * 100).toFixed(0) }}%</strong></span>
    </div>

    <!-- Status-specific messages -->
    <div v-if="status === 'no_usage_fields'" style="font-size:11px;color:var(--text-tertiary);margin-bottom:8px">
      渠道没有返回缓存相关信息，无法判断缓存是否生效。
    </div>
    <div v-if="status === 'no_cache'" style="font-size:11px;color:var(--warning);margin-bottom:8px">
      渠道返回了缓存字段，但值全是 0 — 可能是发送内容没达到缓存最低长度要求，或渠道本身不支持缓存。
    </div>

    <!-- Proxy Cache Warning -->
    <div v-if="report?.proxy_cache?.status === 'detected'" style="font-size:11px;color:var(--warning);margin-bottom:8px;padding:6px 8px;background:var(--warning-bg,#fff8e1);border-radius:4px;border:1px solid var(--warning,#f9a825)">
      这个渠道在中间层做了处理（{{ report.proxy_cache.evidence }}），以下结果测的是渠道的缓存，不是 Claude 的缓存，不具有参考价值。
    </div>

    <!-- Probe Details -->
    <div v-if="report?.probes && report.probes.length" class="diag-probes">
      <template v-for="(probe, pIdx) in report.probes" :key="`${probe.name}:${pIdx}`">
        <div class="diag-probe-card" :class="{ 'diag-probe-anomaly': probeTokenCheck(probe) }">
          <div class="diag-probe-row" @click="toggleProbe(pIdx)">
            <span class="diag-probe-badge" :style="'background:' + probeTokenColor(probe.name, probe.usage?.cache_read_input_tokens > 0 ? 'read' : probe.usage?.cache_creation_input_tokens > 0 ? 'creation' : 'none')">
              {{ diagProbeLabel(probe.name) }}
            </span>
            <span class="diag-probe-tokens">
              <template v-if="probe.usage?.cache_read_input_tokens > 0 && probe.usage?.cache_creation_input_tokens > 0">
                <span class="diag-token-chip diag-token-read">读 {{ probe.usage.cache_read_input_tokens }}</span>
                <span class="diag-token-chip diag-token-create">写 {{ probe.usage.cache_creation_input_tokens }}</span>
              </template>
              <template v-else-if="probe.usage?.cache_read_input_tokens > 0">
                <span class="diag-token-chip diag-token-read">读 {{ probe.usage.cache_read_input_tokens }}</span>
              </template>
              <template v-else-if="probe.usage?.cache_creation_input_tokens > 0">
                <span class="diag-token-chip diag-token-create">写 {{ probe.usage.cache_creation_input_tokens }}</span>
              </template>
              <template v-else>
                <span class="diag-token-chip diag-token-none">无缓存</span>
              </template>
              <span class="diag-probe-latency">{{ probe.latency_ms ? (probe.latency_ms / 1000).toFixed(1) + 's' : '-' }}</span>
              <span v-if="probeTokenCheck(probe)" class="diag-check-badge" :style="'background:' + probeTokenCheck(probe).color + '18;color:' + probeTokenCheck(probe).color" :title="probeTokenCheck(probe).tip">
                {{ probeTokenCheck(probe).text }}
              </span>
            </span>
            <span class="diag-raw-toggle">{{ expandedProbes.has(pIdx) ? '▲' : '▼' }}</span>
          </div>
          <div v-if="expandedProbes.has(pIdx)" class="diag-raw-usage">
            <div v-if="probe.request_preview" class="diag-detail-section">
              <div class="diag-detail-label">请求</div>
              <pre>{{ formatPreview(probe.request_preview) }}</pre>
            </div>
            <div v-if="probe.response_preview" class="diag-detail-section">
              <div class="diag-detail-label">响应</div>
              <pre>{{ probe.response_preview }}</pre>
            </div>
            <div v-if="probe.raw_usage && Object.keys(probe.raw_usage).length" class="diag-detail-section">
              <div class="diag-detail-label">Usage</div>
              <pre>{{ JSON.stringify(probe.raw_usage, null, 2) }}</pre>
            </div>
            <div v-if="probe.expected_total_tokens > 0" class="diag-detail-section">
              <div class="diag-detail-label">Token 校验</div>
              <div class="diag-token-verify">
                <div class="diag-verify-row">
                  <span class="diag-verify-label">缓存区</span>
                  <span class="diag-verify-val">预估 {{ probe.expected_system_tokens }}</span>
                  <span class="diag-verify-arrow">→</span>
                  <span class="diag-verify-val">渠道 {{ (probe.usage?.cache_creation_input_tokens || 0) + (probe.usage?.cache_read_input_tokens || 0) }}</span>
                  <span v-if="(probe.usage?.cache_creation_input_tokens || 0) + (probe.usage?.cache_read_input_tokens || 0) > 0" class="diag-verify-status" :style="'color:' + (
                    (probe.usage.cache_creation_input_tokens + probe.usage.cache_read_input_tokens) > probe.expected_system_tokens * 1.5 ? 'var(--danger)' : 'var(--success)'
                  )">
                    {{ (probe.usage.cache_creation_input_tokens + probe.usage.cache_read_input_tokens) > probe.expected_system_tokens * 1.5 ? '⚠ 疑似注入' : '✓ 正常' }}
                  </span>
                </div>
                <div class="diag-verify-row">
                  <span class="diag-verify-label">总量</span>
                  <span class="diag-verify-val">预估 {{ probe.expected_total_tokens }}</span>
                  <span class="diag-verify-arrow">→</span>
                  <span class="diag-verify-val">渠道 {{ (probe.usage?.input_tokens || 0) + (probe.usage?.cache_creation_input_tokens || 0) + (probe.usage?.cache_read_input_tokens || 0) }}</span>
                  <span v-if="probe.usage?.input_tokens > 0" class="diag-verify-status" :style="'color:' + (
                    (probe.usage.input_tokens + (probe.usage.cache_creation_input_tokens || 0) + (probe.usage.cache_read_input_tokens || 0)) > probe.expected_total_tokens * 2 ? 'var(--danger)' :
                    (probe.usage.input_tokens + (probe.usage.cache_creation_input_tokens || 0) + (probe.usage.cache_read_input_tokens || 0)) < probe.expected_total_tokens * 0.3 ? 'var(--warning)' :
                    'var(--success)'
                  )">
                    {{ (probe.usage.input_tokens + (probe.usage.cache_creation_input_tokens || 0) + (probe.usage.cache_read_input_tokens || 0)) > probe.expected_total_tokens * 2 ? '⚠ 内容注入' :
                       (probe.usage.input_tokens + (probe.usage.cache_creation_input_tokens || 0) + (probe.usage.cache_read_input_tokens || 0)) < probe.expected_total_tokens * 0.3 ? '⚠ 内容丢失' : '✓ 正常' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Run Tag -->
    <div v-if="report?.run_tag" style="font-size:10px;color:var(--text-tertiary);margin-top:4px;font-family:var(--font-mono)">
      run: {{ report.run_tag }}
    </div>

    <!-- Response Cache Warning -->
    <div v-if="report?.response_cache && report.response_cache.status !== 'not_detected'" style="margin-top:6px;font-size:11px;color:var(--warning)">
      检测到响应缓存: {{ report.response_cache.status }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { diagStatusColor, diagStatusLabel, diagStatusTooltip, diagProbeLabel, probeTokenColor, probeTokenCheck } from '../utils/diagnosticUtils.js'

const props = defineProps({
  report: { type: Object, required: true },
  status: { type: String, required: true },
  overallRisk: { type: String, default: '' },
  confidence: { type: Number, default: null },
})

const expandedProbes = ref(new Set())

const hitRate = computed(() => {
  if (props.report?.prompt_cache?.hit_rate != null) return props.report.prompt_cache.hit_rate
  if (props.report?.cache_hit_rate != null) return props.report.cache_hit_rate
  return null
})

function toggleProbe(idx) {
  const s = new Set(expandedProbes.value)
  if (s.has(idx)) s.delete(idx); else s.add(idx)
  expandedProbes.value = s
}

function formatPreview(preview) {
  try { return JSON.stringify(JSON.parse(preview), null, 2) } catch { return preview }
}


</script>

<style scoped>
.diag-result-card {
  padding: 12px 16px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 1px solid var(--border-subtle);
  margin-bottom: 8px;
}

.diag-pending {
  opacity: 0.5;
}

.diag-probes {
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diag-probe-card {
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--bg);
  overflow: hidden;
  transition: border-color 0.15s;
}
.diag-probe-card:hover {
  border-color: var(--border, #d0d0d0);
}
.diag-probe-anomaly {
  background: rgba(239, 68, 68, 0.03);
}

.diag-probe-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.diag-probe-row:hover {
  background: var(--bg-secondary, #fafafa);
}

.diag-probe-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
  min-width: 56px;
  justify-content: center;
}

.diag-probe-tokens {
  display: flex;
  gap: 4px;
  align-items: center;
}

.diag-token-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
}
.diag-token-read {
  background: rgba(34, 197, 94, 0.12);
  color: var(--success, #22c55e);
}
.diag-token-create {
  background: rgba(59, 130, 246, 0.12);
  color: var(--info, #3b82f6);
}
.diag-token-none {
  background: var(--bg-secondary, #f5f5f5);
  color: var(--text-tertiary);
}

.diag-probe-latency {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: 2px;
}

.diag-check-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.diag-raw-toggle {
  font-size: 9px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  width: 16px;
  text-align: center;
  margin-left: auto;
}

.diag-raw-usage {
  padding: 0 10px 10px 10px;
  border-top: 1px solid var(--border-subtle);
}
.diag-detail-section {
  margin-bottom: 6px;
}
.diag-detail-section:last-child {
  margin-bottom: 0;
}
.diag-detail-label {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-bottom: 2px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.diag-raw-usage pre {
  margin: 0;
  padding: 6px 8px;
  background: var(--bg-secondary, #f5f5f5);
  border-radius: 4px;
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
  white-space: pre-wrap;
  word-break: break-all;
}

.diag-token-verify {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  padding: 4px 0;
}
.diag-verify-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.diag-verify-label {
  color: var(--text-tertiary);
  width: 40px;
  flex-shrink: 0;
  font-size: 11px;
}
.diag-verify-val {
  font-family: var(--font-mono);
  font-size: 11px;
}
.diag-verify-arrow {
  color: var(--text-tertiary);
  font-size: 10px;
}
.diag-verify-status {
  font-weight: 600;
  font-size: 11px;
}
</style>
