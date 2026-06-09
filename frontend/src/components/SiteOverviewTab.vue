<template>
  <div class="site-overview-tab">

    <!-- 降级警告 -->
    <div v-if="degradation" class="overview-degradation-warning">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      <span>{{ degradation }}</span>
    </div>

    <!-- 错误类型标签 -->
    <div v-if="errorTypes.length" class="overview-error-tags">
      <span class="overview-error-label">近 {{ totalErrors }} 次错误</span>
      <span v-for="err in errorTypes" :key="err.type" class="overview-error-tag">{{ err.type }} &times; {{ err.count }}</span>
    </div>

    <!-- 无数据空状态 -->
    <div v-if="!modelMetrics.length" class="overview-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <div class="overview-empty-text">该站点尚无测试数据</div>
      <button class="btn btn-primary btn-sm" @click="$emit('go-tab', 'test')">去测试</button>
    </div>

    <!-- 模型指标表 -->
    <div v-else class="overview-table-wrap">
      <table class="overview-table">
        <thead>
          <tr>
            <th>模型</th>
            <th>TTFT P50</th>
            <th>TPOT P50</th>
            <th>E2E P50</th>
            <th>Token/s</th>
            <th>成功率</th>
            <th title="TTFT 延迟变化趋势（7天）">延迟趋势</th>
            <th>监控</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in modelMetrics" :key="m.model">
            <td class="overview-model">{{ m.model }}</td>
            <td :style="latencyColorStyle(m.ttft, 0.5, 2)">{{ fmtTime(m.ttft) }}</td>
            <td :style="latencyColorStyle(m.tpot, 0.01, 0.05)">{{ fmtTime(m.tpot) }}</td>
            <td :style="latencyColorStyle(m.e2e, 1, 5)">{{ fmtTime(m.e2e) }}</td>
            <td class="overview-mono">{{ m.tps != null ? fmtNum(m.tps, 0) + ' t/s' : '-' }}</td>
            <td>
              <span class="rate-badge" :class="rateClass(m.successRate)">{{ fmtPct(m.successRate) }}</span>
            </td>
            <td class="sparkline-cell" :title="latencyTrendTooltip(m.latencyTrend)">
              <svg v-if="m.latencyTrend && m.latencyTrend.length >= 2" width="64" height="20" class="sparkline">
                <polyline
                  :points="sparklinePoints(m.latencyTrend)"
                  fill="none"
                  :stroke="latencyTrendColor(m.latencyTrend)"
                  stroke-width="1.5"
                  stroke-linejoin="round"
                />
                <circle
                  :cx="sparklineEnd(m.latencyTrend).x"
                  :cy="sparklineEnd(m.latencyTrend).y"
                  r="1.8"
                  :fill="latencyTrendColor(m.latencyTrend)"
                />
              </svg>
              <span v-else class="sparkline-na">-</span>
            </td>
            <td class="overview-monitor-cell">
              <template v-if="schedulesLoading">
                <span class="monitor-loading">...</span>
              </template>
              <template v-else>
                <span v-if="getMonitorInfo(m.model)" class="monitor-active">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  {{ getMonitorInfo(m.model) }}
                </span>
                <span v-else class="monitor-inactive">未监控</span>
              </template>
            </td>
            <td class="overview-actions-cell">
              <button class="btn btn-ghost btn-xs" @click="$emit('go-tab', 'test')" title="去测试">测试</button>
              <button class="btn btn-ghost btn-xs" @click="scrollToTrends" title="查看趋势">趋势</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 内嵌趋势 -->
    <div ref="trendsRef" class="overview-trends-section">
      <SiteTrendsTab :profile="profile" />
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { getSchedules } from '../api/index.js';
import { getModelMetrics, sparklinePoints, sparklineEnd, latencyTrendColor, latencyTrendTooltip, getErrorTypes, getTotalErrorCount, getDegradation } from '../utils/siteMetrics.js';
import { fmtTime, fmtPct, fmtNum, latencyColorStyle } from '../utils/formatters.js';
import SiteTrendsTab from './SiteTrendsTab.vue';

const props = defineProps({
  profile: { type: Object, required: true },
  siteSummary: { type: Object, default: null },
});

defineEmits(['go-tab']);

const trendsRef = ref(null);
const schedulesLoading = ref(false);
const schedules = ref([]);

// 从 siteSummary 计算指标（若无数据则返回空数组）
const modelMetrics = computed(() => {
  if (!props.siteSummary) return [];
  return getModelMetrics(props.siteSummary);
});

const degradation = computed(() => {
  if (!props.siteSummary) return null;
  return getDegradation(props.siteSummary);
});

const errorTypes = computed(() => {
  if (!props.siteSummary) return [];
  return getErrorTypes(props.siteSummary);
});

const totalErrors = computed(() => {
  if (!props.siteSummary) return 0;
  return getTotalErrorCount(props.siteSummary);
});

// 成功率徽章样式
function rateClass(rate) {
  if (rate == null) return '';
  if (rate >= 95) return 'success';
  if (rate >= 80) return 'accent';
  return 'danger';
}

// 监控状态：精确实现
// 任务通过 profile_ids 关联站点，模型列表在 configs / configs_json 中
function getModelListFromSchedule(s) {
  let configs = s.configs;
  if (!configs && s.configs_json) {
    try {
      configs = typeof s.configs_json === 'string' ? JSON.parse(s.configs_json) : s.configs_json;
    } catch {
      configs = {};
    }
  }
  configs = configs || {};
  return configs.models || (configs.model ? [configs.model] : []);
}

function getMonitorInfo(model) {
  const profileName = props.profile?.name;
  if (!profileName) return null;
  // 找到属于本站点的 active 任务，且覆盖该模型
  const matched = schedules.value.find(s =>
    s.status === 'active' &&
    (s.profile_ids || []).includes(profileName) &&
    getModelListFromSchedule(s).includes(model)
  );
  if (!matched) return null;
  const sv = parseInt(matched.schedule_value) || 0;
  if (sv <= 0) return '监控中';
  if (sv < 3600) {
    const mins = Math.round(sv / 60);
    return `每${mins}分钟`;
  }
  const hrs = Math.round(sv / 3600);
  return `每${hrs}小时`;
}

function scrollToTrends() {
  trendsRef.value?.scrollIntoView({ behavior: 'smooth' });
}

onMounted(async () => {
  schedulesLoading.value = true;
  try {
    const data = await getSchedules();
    schedules.value = data.schedules || [];
  } catch {
    schedules.value = [];
  }
  schedulesLoading.value = false;
});
</script>

<style scoped>
.site-overview-tab {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ---- 降级警告 ---- */
.overview-degradation-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  background: var(--warning-light, #fef3cd);
  color: var(--warning, #d97706);
  font-size: 12px;
  font-weight: 600;
}

/* ---- 错误标签 ---- */
.overview-error-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.overview-error-label {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.overview-error-tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--danger-light, #fee2e2);
  color: var(--danger, #dc2626);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

/* ---- 空状态 ---- */
.overview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
  color: var(--text-tertiary);
}

.overview-empty-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

/* ---- 指标表 ---- */
.overview-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  background: var(--surface-raised);
}

.overview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.overview-table th {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  background: var(--bg-secondary, var(--surface-raised));
}

.overview-table td {
  padding: 7px 10px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
  white-space: nowrap;
}

.overview-table tbody tr:last-child td {
  border-bottom: none;
}

.overview-table tbody tr:hover td {
  background: var(--border-subtle);
}

.overview-model {
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.overview-mono {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* ---- Sparkline ---- */
.sparkline-cell {
  padding: 4px 8px !important;
  vertical-align: middle;
}

.sparkline {
  display: block;
  vertical-align: middle;
}

.sparkline-na {
  color: var(--text-tertiary);
  font-size: 11px;
}

/* ---- 监控状态 ---- */
.overview-monitor-cell {
  min-width: 80px;
}

.monitor-active {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--success);
  font-size: 11px;
  font-weight: 600;
}

.monitor-inactive {
  color: var(--text-tertiary);
  font-size: 11px;
}

.monitor-loading {
  color: var(--text-tertiary);
  font-size: 11px;
}

/* ---- 操作列 ---- */
.overview-actions-cell {
  display: flex;
  gap: 4px;
  align-items: center;
}

.btn-xs {
  padding: 2px 8px !important;
  font-size: 11px !important;
  height: auto !important;
  line-height: 1.6 !important;
}

/* ---- 内嵌趋势区 ---- */
.overview-trends-section {
  margin-top: 4px;
}
</style>
