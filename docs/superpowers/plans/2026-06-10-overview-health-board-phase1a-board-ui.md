# 站点健康看板 · 阶段一·a（站点页看板 UI）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 把「目标站点」页（`SitesView.vue`）从卡片网格升级为**站点×模型健康看板**：站点行（各模型**平均**）默认收起、点开看模型，每格带**状态页式可用性柱**（消费阶段零的 `/api/sites/availability`），异常置顶，顶部全局健康条。先只改 `/sites` 页本身；概览合并与导航改动放阶段一·b。

**Architecture:** 纯前端。新增 1 个 api 调用 + 3 个 `siteMetrics.js` 纯函数（vitest 覆盖）；`SitesView.vue` 复用现有 `getModelMetrics`（per-模型指标）+ 新可用性接口，渲染两层可展开表 + 可用性柱。保留现有搜索/筛选/收藏/新建/一键测试逻辑。

**Tech Stack:** Vue 3 + Pinia + Vite；单测 `bunx vitest run`；构建 `bun run build`。**前端用 bun，不用 npm。**

**工作目录：** `/Users/yakun/linkingrid/AITokenPerf/.claude/worktrees/issue-58-overview-health-board`（分支 `feat/issue-58-overview-health-board`，已含阶段零端点 + 前端依赖已 `bun install`）。

**关联设计：** `docs/superpowers/specs/2026-06-10-overview-health-board-ia-redesign-design.md` §5.1/§5.3/§9.1。可用性柱 = 时间桶；三档着色 绿≥95/橙80–95/红<80；站点行 = 各模型同桶平均；默认全收起、不记忆展开。

---

## File Structure
- **Modify** `frontend/src/api/index.js`：新增 `getCellAvailability`。
- **Modify** `frontend/src/utils/siteMetrics.js`：新增纯函数 `availabilityClass` / `buildAvailabilityLookup` / `siteAvgSeries`。
- **Create** `frontend/src/utils/__tests__/siteMetrics.test.js`：上述纯函数的 vitest 单测。
- **Modify** `frontend/src/views/SitesView.vue`：卡片网格 → 看板表（站点行可展开 + 可用性柱 + 全局健康条），保留工具栏/收藏/新建/一键测试。

---

## Task 1: api + 纯函数（TDD）

**Files:** Modify `frontend/src/api/index.js`、`frontend/src/utils/siteMetrics.js`；Create `frontend/src/utils/__tests__/siteMetrics.test.js`

- [ ] **Step 1: 写失败测试** — 新建 `frontend/src/utils/__tests__/siteMetrics.test.js`：

```js
import { describe, it, expect } from 'vitest';
import { availabilityClass, buildAvailabilityLookup, siteAvgSeries } from '../siteMetrics';

describe('availabilityClass', () => {
  it('按阈值分三档 + 空值', () => {
    expect(availabilityClass(null)).toBe('na');
    expect(availabilityClass(100)).toBe('up');
    expect(availabilityClass(95)).toBe('up');
    expect(availabilityClass(94.9)).toBe('degraded');
    expect(availabilityClass(80)).toBe('degraded');
    expect(availabilityClass(79.9)).toBe('down');
    expect(availabilityClass(0)).toBe('down');
  });
});

describe('buildAvailabilityLookup', () => {
  it('cells 数组 → {profile:{model:series}}', () => {
    const lut = buildAvailabilityLookup([
      { profile: 'S', model: 'm', series: [100, null, 80] },
      { profile: 'S', model: 'n', series: [90] },
    ]);
    expect(lut.S.m).toEqual([100, null, 80]);
    expect(lut.S.n).toEqual([90]);
  });
  it('空/缺省安全', () => {
    expect(buildAvailabilityLookup()).toEqual({});
    expect(buildAvailabilityLookup([{ profile: 'A', model: 'x' }]).A.x).toEqual([]);
  });
});

describe('siteAvgSeries', () => {
  it('各模型同桶平均，忽略 null 空桶', () => {
    // 桶0: avg(100,80)=90; 桶1: 只有第二个 60 → 60; 桶2: 都 null → null
    expect(siteAvgSeries([[100, null, null], [80, 60, null]])).toEqual([90, 60, null]);
  });
  it('空输入 → []', () => {
    expect(siteAvgSeries([])).toEqual([]);
    expect(siteAvgSeries([[], []])).toEqual([]);
  });
});
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd frontend && bunx vitest run src/utils/__tests__/siteMetrics.test.js`
Expected: FAIL（`availabilityClass` 等未导出）。

- [ ] **Step 3: 实现纯函数** — 在 `frontend/src/utils/siteMetrics.js` 末尾追加：

```js
// 可用性着色：成功率(%) → 档位。阈值 绿≥95 / 橙80–95 / 红<80；空桶=na
export function availabilityClass(rate) {
  if (rate == null) return 'na';
  if (rate >= 95) return 'up';
  if (rate >= 80) return 'degraded';
  return 'down';
}

// /api/sites/availability 的 cells 数组 → 查找表 {profile: {model: series}}
export function buildAvailabilityLookup(cells) {
  const lut = {};
  for (const c of cells || []) {
    if (!lut[c.profile]) lut[c.profile] = {};
    lut[c.profile][c.model] = c.series || [];
  }
  return lut;
}

// 站点级可用性序列 = 各模型同一桶成功率平均（忽略 null 空桶）；无数据→[]
export function siteAvgSeries(modelSeriesList) {
  const lists = (modelSeriesList || []).filter(s => Array.isArray(s) && s.length);
  if (!lists.length) return [];
  const n = Math.max(...lists.map(s => s.length));
  const out = [];
  for (let i = 0; i < n; i++) {
    const vals = lists.map(s => s[i]).filter(v => v != null);
    out.push(vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null);
  }
  return out;
}
```

- [ ] **Step 4: 加 api** — 在 `frontend/src/api/index.js` 的 `getSitesSummary` 之后追加：

```js
export const getCellAvailability = ({ hours, buckets } = {}) => {
  const params = new URLSearchParams();
  if (hours != null) params.set('hours', hours);
  if (buckets != null) params.set('buckets', buckets);
  const qs = params.toString();
  return api('/api/sites/availability' + (qs ? '?' + qs : ''));
};
```

- [ ] **Step 5: 运行，确认通过**

Run: `cd frontend && bunx vitest run src/utils/__tests__/siteMetrics.test.js`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/index.js frontend/src/utils/siteMetrics.js frontend/src/utils/__tests__/siteMetrics.test.js
git commit -m "feat(web): 看板可用性纯函数 + getCellAvailability 接口 (#58)"
```

---

## Task 2: SitesView 看板渲染

**Files:** Modify `frontend/src/views/SitesView.vue`

> 这是对现有 886 行组件的**改造**，不是从零重写。**保留**：`<script setup>` 里的收藏(favorites)、搜索/状态筛选、`filteredSites` 排序、新建站点 modal（`createSite`/`submitCreate`）、一键测试（`testSite`/`confirmTest`/`pollTestCompletion`）、`getModelMetrics`/sparkline 引用、time-range watch。**替换**：把"卡片网格"那段模板换成下面的看板表；**新增**：可用性数据加载 + 展开状态 + 全局健康条。

- [ ] **Step 1: 数据加载加可用性** — 修改 `loadData()`：在拿到 summary 后并行取可用性并建查找表。

```js
import { getSitesSummary, getCellAvailability } from '../api';
import { getModelMetrics, /* …保留原有… */ availabilityClass, buildAvailabilityLookup, siteAvgSeries } from '../utils/siteMetrics';

const availabilityLut = ref({});
const BUCKETS = 24;

async function loadData() {
  loading.value = true;
  try {
    const [summaryData, availData] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }),
      getCellAvailability({ hours: timeRangeStore.hours, buckets: BUCKETS }).catch(() => ({ cells: [] })),
    ]);
    sites.value = summaryData.summary || [];
    availabilityLut.value = buildAvailabilityLookup(availData.cells || []);
  } catch (e) {
    toast('加载站点数据失败: ' + e.message, 'error');
  }
  loading.value = false;
}
```

- [ ] **Step 2: 展开状态（不持久化）+ 行数据 helper**

```js
const expanded = ref(new Set());
function toggleExpand(name) {
  const next = new Set(expanded.value);
  next.has(name) ? next.delete(name) : next.add(name);
  expanded.value = next;
}
function isExpanded(name) { return expanded.value.has(name); }

// 某站点的模型行（复用现有 per-模型指标）+ 每模型可用性序列
function modelRows(site) {
  const lut = availabilityLut.value[site.profile.name] || {};
  return getModelMetrics(site).map(m => ({ ...m, series: lut[m.model] || [] }));
}
// 站点行可用性 = 各模型同桶平均
function siteSeries(site) {
  const lut = availabilityLut.value[site.profile.name] || {};
  return siteAvgSeries(Object.values(lut));
}
// 站点行聚合 TTFT / 成功率 = 各模型平均（用于站点行展示）
function siteAvg(site, key) {
  const vals = getModelMetrics(site).map(m => m[key]).filter(v => v != null);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
// 全局健康条计数
const healthCounts = computed(() => {
  const c = { error: 0, healthy: 0, untested: 0 };
  for (const s of sites.value) c[s.health] = (c[s.health] || 0) + 1;
  return c;
});
```

- [ ] **Step 3: 可用性柱子组件（行内渲染）** — 在模板里用一个小的渲染片段（无需单独文件）。柱：一排 `<i>`，class 由 `availabilityClass(rate)` 决定。

```html
<span class="avail-bars">
  <i v-for="(rate, i) in series" :key="i" :class="'ab-' + availabilityClass(rate)"
     :title="rate == null ? '无数据' : ('成功率 ' + rate.toFixed(1) + '%')"></i>
</span>
```

- [ ] **Step 4: 替换卡片网格为看板表** — 把 `<div class="sites-grid">…</div>`（含 `site-card`）整段替换为：

```html
<div v-else class="board-wrap">
  <!-- 全局健康条 -->
  <div class="health-bar">
    <span class="hb-pill err"><span class="dot dr"></span>异常 {{ healthCounts.error }}</span>
    <span class="hb-pill ok"><span class="dot dg"></span>健康 {{ healthCounts.healthy }}</span>
    <span class="hb-pill un"><span class="dot du"></span>未测 {{ healthCounts.untested }}</span>
    <span class="hb-legend"><i class="ab-up"></i>可用 <i class="ab-degraded"></i>降级 <i class="ab-down"></i>不可用</span>
  </div>
  <table class="board">
    <thead><tr>
      <th></th><th>站点 / 模型</th><th>可用性 · 近{{ BUCKETS }}</th>
      <th>TTFT P50</th><th>趋势</th><th>Token/s</th><th>成功率</th><th>最近测试</th>
    </tr></thead>
    <tbody>
      <template v-for="site in filteredSites" :key="site.profile.name">
        <!-- 站点行 -->
        <tr class="site-row" :class="'h-' + site.health" @click="toggleExpand(site.profile.name)">
          <td><span class="dot" :class="'d-' + site.health"></span></td>
          <td>
            <span class="chev" :class="{ open: isExpanded(site.profile.name) }">▸</span>
            <button class="fav" :class="{ on: isFavorite(site.profile.name) }" @click.stop="toggleFavorite(site.profile.name)">★</button>
            <router-link class="sname" :to="`/sites/${encodeURIComponent(site.profile.name)}`" @click.stop>{{ site.profile.name }}</router-link>
            <span class="mcount">{{ getModelMetrics(site).length }} 模型</span>
          </td>
          <td><span class="avail-bars"><i v-for="(rate,i) in siteSeries(site)" :key="i" :class="'ab-'+availabilityClass(rate)" :title="rate==null?'无数据':('成功率 '+rate.toFixed(1)+'%')"></i></span></td>
          <td>{{ siteAvg(site,'ttft') != null ? fmtTime(siteAvg(site,'ttft')) : '-' }} <span class="agg">平均</span></td>
          <td></td>
          <td>{{ siteAvg(site,'tps') != null ? fmtNum(siteAvg(site,'tps'),0) : '-' }}</td>
          <td><span class="rate" :class="rateClass(siteAvg(site,'successRate'))">{{ siteAvg(site,'successRate')!=null ? fmtPct(siteAvg(site,'successRate')) : '-' }}</span></td>
          <td>{{ site.last_test_at ? relativeTime(site.last_test_at) : '未测试' }}</td>
        </tr>
        <!-- 模型行（展开时）-->
        <tr v-for="m in (isExpanded(site.profile.name) ? modelRows(site) : [])" :key="site.profile.name + '/' + m.model" class="model-row">
          <td></td>
          <td class="mname">{{ m.model }}</td>
          <td><span class="avail-bars sm"><i v-for="(rate,i) in m.series" :key="i" :class="'ab-'+availabilityClass(rate)" :title="rate==null?'无数据':('成功率 '+rate.toFixed(1)+'%')"></i></span></td>
          <td :style="latencyColorStyle(m.ttft, 0.5, 2)">{{ m.ttft!=null ? fmtTime(m.ttft) : '-' }}</td>
          <td class="spark-cell">
            <svg v-if="m.latencyTrend && m.latencyTrend.length>=2" width="64" height="20" class="sparkline">
              <polyline :points="sparklinePoints(m.latencyTrend)" fill="none" :stroke="latencyTrendColor(m.latencyTrend)" stroke-width="1.5"/>
            </svg><span v-else class="spark-na">-</span>
          </td>
          <td>{{ m.tps!=null ? fmtNum(m.tps,0) : '-' }}</td>
          <td><span class="rate" :class="rateClass(m.successRate)">{{ m.successRate!=null ? fmtPct(m.successRate) : '-' }}</span></td>
          <td>一键测试 / 详情 → 用站点行；模型行只读</td>
        </tr>
      </template>
    </tbody>
  </table>
  <!-- 行内操作：在站点行尾或悬浮提供"一键测试 / 详情→"，复用现有 testSite/goDetail；可放每个站点行末列或 hover 工具条。保留原 confirmTarget modal。 -->
</div>
```

> 说明：保留原有 `testSite(site)`、`goDetail(site)`、确认测试 modal、新建站点 modal、空状态、加载态。"一键测试/详情"按钮可放在站点行 hover 出现的小工具条里（自行决定位置，别破坏点击展开）。模型行的"最近测试"列那句占位文案删掉、留空即可。

- [ ] **Step 5: CSS（scoped）** — 追加可用性柱、表格、行、chevron 等样式：

```css
.avail-bars { display:inline-flex; align-items:flex-end; gap:1.5px; }
.avail-bars i { display:inline-block; width:4px; height:16px; border-radius:1px; background:var(--border); }
.avail-bars.sm i { height:13px; }
.avail-bars i.ab-up { background:#21a366; }
.avail-bars i.ab-degraded { background:#f5a623; }
.avail-bars i.ab-down { background:#e5484d; }
.avail-bars i.ab-na { background:var(--border-subtle, #e5e5e5); }
table.board { width:100%; border-collapse:collapse; font-size:12.5px; }
table.board th { text-align:left; font-size:10px; text-transform:uppercase; color:var(--text-tertiary); padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }
table.board td { padding:8px 10px; border-bottom:1px solid var(--border-subtle); white-space:nowrap; vertical-align:middle; }
.site-row { cursor:pointer; } .site-row:hover td { background:var(--border-subtle); }
.site-row.h-error td { background:#fef6f6; }
.model-row td { background:var(--bg, #fafafa); }
.mname { padding-left:26px; color:var(--text-secondary); font-weight:600; }
.chev { display:inline-block; width:14px; color:var(--text-tertiary); font-size:10px; transition:transform .15s; }
.chev.open { transform:rotate(90deg); }
.sname { font-weight:700; color:var(--text-primary); text-decoration:none; }
.sname:hover { color:var(--accent); }
.mcount { font-size:10.5px; font-weight:600; color:#6b7280; background:var(--border-subtle); border-radius:999px; padding:1px 7px; margin-left:6px; }
.fav { background:none; border:none; cursor:pointer; color:var(--text-tertiary); }
.fav.on { color:var(--warning); }
.agg { font-size:9px; color:var(--text-tertiary); }
.health-bar { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hb-pill { font-size:12px; font-weight:700; padding:5px 11px; border-radius:999px; display:flex; align-items:center; gap:6px; }
.hb-pill.err { background:#fdecec; color:#c0282d; } .hb-pill.ok { background:#e7f6ec; color:#1a7f43; } .hb-pill.un { background:#eee; color:#777; }
.hb-legend { margin-left:auto; font-size:11px; color:var(--text-tertiary); display:flex; align-items:center; gap:6px; }
.hb-legend i { display:inline-block; width:9px; height:11px; border-radius:1px; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.d-healthy, .dg { background:var(--success); } .d-error, .dr { background:var(--danger); } .d-untested, .du { background:var(--text-tertiary); }
```

- [ ] **Step 6: 构建 + 冒烟**

Run: `cd frontend && bun run build`
Expected: 构建成功，无报错。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/SitesView.vue
git commit -m "feat(web): 站点页升级为站点×模型健康看板（可用性柱+可展开）(#58)"
```

---

## Self-Review
- **Spec 覆盖**：站点行平均聚合(siteAvg/siteAvgSeries)✓；可展开模型行✓；时间桶可用性柱+三档着色(availabilityClass)✓；默认收起、不记忆(expanded Set 每次加载不恢复)✓；异常置顶(沿用 filteredSites 排序)✓；全局健康条✓；消费阶段零端点(getCellAvailability)✓。保留收藏/搜索/筛选/新建/一键测试✓。
- **范围**：仅 `/sites` 页；概览合并 + 导航改动属阶段一·b，不在本计划。
- **占位符**：Task 1 全代码 + 测试；Task 2 是对现有组件的具体改造说明 + 关键新代码片段（柱/表/展开/数据加载/CSS 均给出），实现者据此改 `SitesView.vue` 并保留既有逻辑。
- **测试**：纯函数 vitest；UI 以 `bun run build` 通过为门槛（无法在 CLI 里做视觉验证，需人工浏览器确认）。
- **类型一致**：`availabilityClass`/`buildAvailabilityLookup`/`siteAvgSeries`/`getCellAvailability` 在 api、util、测试、SitesView 间命名一致；端点返回 `{cells:[{profile,model,series}]}` 与 buildAvailabilityLookup 入参一致。
