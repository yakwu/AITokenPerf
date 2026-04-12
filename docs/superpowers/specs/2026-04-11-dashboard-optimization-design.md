# 概览页及多页面优化设计文档

**日期**: 2026-04-11
**范围**: 15 项优化，涵盖概览页、目标站点页、历史与对比页、定时任务页、右上角浮窗

---

## 1. 概览页站点状态排序 (#1)

**现状**: `sites` 数组按 API 返回顺序渲染，无排序逻辑。

**方案**: 在 `DashboardView.vue` 中新增 `sortedSites` computed，替代模板中直接使用 `sites`。

排序规则（优先级从高到低）：
1. health 分组权重：`error=0, healthy=1, untested=2, unknown=2`
2. 同组内按 `last_test_at` 降序（最近测试的排前面）
3. 无 `last_test_at` 的排最后

```javascript
const healthOrder = { error: 0, healthy: 1, untested: 2, unknown: 2 };
const sortedSites = computed(() =>
  [...sites.value].sort((a, b) => {
    const ha = healthOrder[a.health] ?? 2;
    const hb = healthOrder[b.health] ?? 2;
    if (ha !== hb) return ha - hb;
    return (b.last_test_at || '').localeCompare(a.last_test_at || '');
  })
);
```

模板中 `v-for="site in sites"` 改为 `v-for="site in sortedSites"`。

---

## 2. 目标站点数分组 (#2)

**现状**: 只显示 `healthyCount` 一个 sub 标签。

**方案**: 增加 `errorCount` 和 `untestedCount` computed，模板中按条件展示三个 sub 标签。

```html
<span v-if="errorCount > 0" class="dash-summary-sub danger">{{ errorCount }} 异常</span>
<span v-if="healthyCount > 0" class="dash-summary-sub success">{{ healthyCount }} 健康</span>
<span v-if="untestedCount > 0" class="dash-summary-sub muted">{{ untestedCount }} 未测试</span>
```

---

## 3. 活跃定时任务 tooltip (#3)

**现状**: 标签 "活跃定时任务" 含义不清晰。

**方案**: 给标签加 `title` 属性。

```html
<div class="dash-summary-label" title="状态为「运行中」的定时任务数量">活跃定时任务 ...</div>
```

---

## 4. 测试数标签修正 (#4)

**现状**: 标签 "今日测试数"，逻辑硬编码过滤今天日期前缀，与右上角时间筛选不一致。

**方案**:
- 标签改为 "测试数"
- 值改为 `results.value.length`（即当前时间范围内的结果总数）
- 加 `title` tooltip: "当前时间范围内的测试结果记录总数"

---

## 5. 整体成功率字段名 BUG (#5)

**现状**: `DashboardView.vue` 中多处使用 `r.summary?.successful_requests`，但后端返回的字段名为 `success_count`，导致成功率始终计算为 0。

**涉及行**:
- 第 185 行: `overallSuccessRate` computed
- 第 198 行: `yesterdayRate` computed
- 第 238-239 行: `alerts` computed
- 第 341-343 行: `getSiteLatestMetrics` 函数

**方案**: 所有 `successful_requests` 替换为 `success_count`。

---

## 6. 覆盖模型数/厂商 hover tooltip (#6)

**现状**: 只显示数量，hover 无提示。

**方案**: 给卡片区域添加自定义 hover tooltip。

新增 computed:
- `modelList`: 去重的模型名称列表
- `vendorList`: 去重的厂商名称列表

用 `title` 属性或自定义 CSS tooltip 显示完整列表：
```html
<div class="dash-summary-card" :title="'模型: ' + modelList.join(', ') + '\n厂商: ' + vendorList.join(', ')">
```

如果列表太长（超过 10 个），截断显示前 10 个并追加 "...等 N 个"。

---

## 7. 最近活动数据修正 (#7)

**现状**: Dashboard 调用 `getResults({ limit: 100, hours, fields: 'summary' })`，后端 `get_results_aggregated()` 将同一定时任务的结果聚合为一条，导致最近活动展示的是聚合条目而非逐条记录。

**方案**:

### 后端 (`app/db.py`)

在 `get_results_aggregated()` 函数中增加 `raw: bool = False` 参数：
- `raw=True` 时跳过聚合逻辑，直接返回按 `created_at DESC` 排序的原始结果，保留 `limit/offset/hours` 分页和时间过滤
- `raw=False` 时保持现有聚合行为（向后兼容）

### 后端 (`app/server.py`)

`/api/results` 端点增加 `raw` query 参数，传递给 `get_results_aggregated()`。

### 前端 (`DashboardView.vue`)

```javascript
getResults({ limit: 100, hours: timeRangeStore.hours, fields: 'summary', raw: true })
```

---

## 8. 站点名跳转统一 (#8)

**现状**:
- 站点状态列表 `goSiteDetail()` → `/sites/{name}`（默认第一个 tab）
- 异常告警 `goSiteHistory()` → `/sites/{name}?tab=trends`（已正确）
- 定时任务页站点链接 → `/sites/{name}`（默认第一个 tab）

**方案**:
- `DashboardView.vue`: `goSiteDetail()` 改为 `router.push(/sites/${name}?tab=trends)`
- `TasksView.vue`: router-link 的 `:to` 加上 `?tab=trends`

---

## 9. 目标站点页排序 (#9)

**现状**: `SitesView.vue` 站点卡片无排序。

**方案**: 同 #1 的排序逻辑，在 `SitesView.vue` 的 `filteredSites` computed 末尾加排序。

排序在搜索和状态筛选之后执行，规则一致：`error > healthy > untested`，组内按 `last_test_at` 降序。

---

## 10. 历史与对比取消分组 (#10)

**现状**: `HistoryView.vue` 使用聚合数据，同一定时任务的结果折叠为一行（带 children_count badge），可展开查看子记录。

**方案**:

### 前端 (`HistoryView.vue`)

- API 调用增加 `raw=true` 参数（复用 #7 的后端改动）
- 移除所有 group 相关逻辑：
  - `isGroup()` 函数
  - `expandedGroups` ref
  - group children 模板块（`v-if="isGroup(r) && expandedGroups.has(idx)"` 整块）
  - `toggleGroupChildDetail` / `groupChildDetailOpen` / `groupChildDetailHtml` 等方法
- 每条结果独立显示，保留现有的行展开详情功能
- 分页保持不变（20 条/页）

### "来源"列调整

移除分组后，"来源"列简化为：
- 有 `schedule_name` → 显示任务名
- 无 → 显示 "手动"

---

## 11. "全部站点"筛选 (#11)

**现状**: `FilterDropdown v-model="siteFilter" :options="uniqueProfiles" all-label="全部站点"` 按 `config.profile_name` 筛选。

**结论**: 功能正确，label 合理。**无需修改**。

---

## 12. 趋势 tab 增加执行记录表格 (#12)

**现状**: `SiteTrendsTab.vue` 只有趋势图和 summary 卡片，无执行记录列表。

**方案**: 在趋势图下方增加"执行记录"表格。

### 数据源

调用现有 API: `/api/schedules/{id}/results?limit=20&offset=X`（如有定时任务）或 `/api/results?raw=true&hours=X`（按站点 base_url 过滤）。

考虑到站点可能有多个定时任务和手动测试，使用 `/api/results?raw=true` 并在前端按 `config.profile_name` 过滤更合适。

### 表格列

| 列 | 说明 |
|---|------|
| 时间 | 格式化 timestamp |
| 模型 | config.model |
| 并发 | config.concurrency |
| 成功率 | summary.success_rate（颜色编码） |
| TTFT P50 | percentiles.TTFT.P50 |
| Token/s | summary.token_throughput_tps |
| 来源 | 定时任务名 / 手动 |

### 分页

20 条/页，使用后端 offset/limit 分页。

### 行交互

点击行可展开详情（复用 `renderResultDetail()`）。

---

## 13. "测试" 改名为 "单次任务" (#13)

**现状**: `SiteDetailView.vue` 的第一个 tab 名称为 "测试"。

**方案**: 标签文字改为 "单次任务"。仅改 label，组件和路由不变。

---

## 14. 单次任务 tab 样式统一 (#14)

**现状**: `SiteTestTab.vue` 的部分样式元素与整体风格不一致。

**需要对齐的样式点**:
- `.form-label`、`.form-input`、`.form-textarea` 确保使用全局变量
- `.radio-pill` 和 `.chip` 组件样式对齐全局 pill/chip 风格
- `.combobox` 样式对齐其他页面的 dropdown 风格
- `.progress-panel` 内的 card 样式使用 `var(--surface-raised)` 而非 `var(--bg)`
- `.info-tip` 样式统一
- `.btn-group` 间距和尺寸对齐全局按钮

具体做法：逐一检查 scoped style 中的硬编码值，替换为全局 CSS 变量，确保视觉一致。

---

## 15. 右上角浮窗改为实时执行状态 (新增)

**现状**: `ScheduleIndicator.vue` 显示 `status=active` 的定时任务列表，与概览页卡片信息重复。

**方案**: 改为显示"此刻正在执行 benchmark 的任务"。

### 后端

`BenchTaskManager` 新增方法：
```python
def get_user_running_tasks(self, user_id: int) -> list[BenchTask]:
    return [t for t in self._tasks.values()
            if t.owner_id == user_id and t.status == "running"]
```

新增端点 `GET /api/bench/running`：
```json
{
  "tasks": [
    {
      "task_id": "xxx",
      "model": "gpt-4",
      "profile_name": "openai-prod",
      "scheduled_task_id": 5,
      "done": 30,
      "total": 100,
      "success": 28,
      "failed": 2,
      "elapsed": 12.5
    }
  ]
}
```

### 前端 (`ScheduleIndicator.vue`)

- 数据源从 `getSchedules()` 改为轮询 `/api/bench/running`（间隔 5 秒）
- 无 running task 时整个组件隐藏
- Pill 文案: "X 执行中"
- 展开面板显示每个任务：模型名、站点名、进度条（done/total）、耗时
- 面板底部链接: 如有 `scheduled_task_id` 则跳对应站点趋势页，手动任务跳对应站点单次任务 tab

---

## 文件变更总览

| 文件 | 改动类型 | 涉及项 |
|------|----------|--------|
| `app/db.py` | 修改 | #7, #10: `get_results_aggregated` 增加 raw 参数 |
| `app/server.py` | 修改 | #7, #10: `/api/results` 增加 raw 参数; #15: 新增 `/api/bench/running` 端点 |
| `frontend/src/views/DashboardView.vue` | 修改 | #1, #2, #3, #4, #5, #6, #7, #8 |
| `frontend/src/views/SitesView.vue` | 修改 | #9: 排序逻辑 |
| `frontend/src/views/HistoryView.vue` | 修改 | #10: 移除分组逻辑 |
| `frontend/src/views/TasksView.vue` | 修改 | #8: 站点链接加 ?tab=trends |
| `frontend/src/views/SiteDetailView.vue` | 修改 | #13: tab 标签改名 |
| `frontend/src/components/SiteTestTab.vue` | 修改 | #14: 样式统一 |
| `frontend/src/components/SiteTrendsTab.vue` | 修改 | #12: 增加执行记录表格 |
| `frontend/src/components/ScheduleIndicator.vue` | 修改 | #15: 改为实时执行状态 |
| `frontend/src/api/index.js` | 修改 | #15: 新增 `getRunningTasks()` API 函数 |
