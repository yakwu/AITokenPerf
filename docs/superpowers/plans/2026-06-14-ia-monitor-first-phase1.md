# IA 重构 · 阶段一（监控总览地基）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭出"监控总览 `/monitor`"主着陆页所需的地基（当前告警聚合端点 + 健康看板组件抽离 + 查询性能护栏），并组装 MonitorView、完成导航/路由切换与飞书卡片加链接。

**Architecture:** 后端新增一个纯函数 `aggregate_active_alerts`（把各任务私有的 `alert_state` JSON 解开、筛出正在告警的格子、按站点×模型合并）+ 一个只读端点 `GET /api/alerts/active`；前端把 `SitesView` 内联的健康看板抽成可复用组件 `SiteHealthBoard.vue`，由新页 `MonitorView.vue` 与瘦身后的 `/sites` 共用；路由把 `/` 与 `/tasks` 指向 `/monitor`。

**Tech Stack:** 后端 FastAPI + SQLAlchemy(async) + pytest(asyncio)；前端 Vue 3 `<script setup>` + vue-router + Pinia + Vitest。包管理用 **bun**。

**对应**：spec `docs/superpowers/specs/2026-06-14-ia-monitor-first-redesign-design.md` §6/§11/§15 的阶段 1a + 1b。本阶段**不**改站点列表瘦身、tab 重排、新建合一、模型归并（那是阶段 2-4）。

---

## 文件结构

| 文件 | 责任 | 动作 |
|------|------|------|
| `app/notifier.py` | 新增纯函数 `aggregate_active_alerts(tasks)`；`build_feishu_card` 增加跳转链接 | 修改 |
| `app/server.py` | 新增 `GET /api/alerts/active` 端点 | 修改 |
| `app/config.py` | 新增 `APP_PUBLIC_URL` 读取（飞书卡片链接用） | 修改 |
| `app/db.py` | results 查询加 `(user_id, timestamp)` 索引护栏 | 修改 |
| `tests/test_alert_api.py` | `aggregate_active_alerts` 单测 + `/api/alerts/active` 接口测试 | 修改 |
| `tests/test_notifier.py` | 飞书卡片含链接的断言 | 修改 |
| `frontend/src/components/SiteHealthBoard.vue` | 站点×模型健康看板组件（从 SitesView 抽出） | 创建 |
| `frontend/src/views/SitesView.vue` | 改为使用 `SiteHealthBoard` 组件 | 修改 |
| `frontend/src/views/MonitorView.vue` | 监控总览：状态条 + 当前告警 + 健康看板 + 任务折叠 | 创建 |
| `frontend/src/api.js` | 新增 `getActiveAlerts()` | 修改 |
| `frontend/src/router.js` | `/monitor` 路由；`/`、`/tasks` 重定向 | 修改 |
| `frontend/src/App.vue` | 顶导加"监控总览"、"站点"改"站点管理" | 修改 |
| `frontend/src/components/__tests__/SiteHealthBoard.test.js` | 组件渲染冒烟测试 | 创建 |

---

## Task 1：`aggregate_active_alerts` 纯函数（后端）

把各任务的 `alert_state` 解开，筛出 `state=alerting` 的格子，按 `(profile, model)` 合并，标注所属任务。纯函数、不碰 DB，便于快速单测。

`alert_state` 形如 `{"<profile名>": {"<model>": {"s":"alerting","n":2}}}`（见 `app/scheduler.py:250-260`）。`profile` 键即站点名。注意 `alert_state` **不保存成功率**，只存状态+连续计数，故端点只返回 streak，前端再与健康表 join 出成功率。

**Files:**
- Modify: `app/notifier.py`（在 `_cell_state` 之后插入）
- Test: `tests/test_alert_api.py`

- [ ] **Step 1: 写失败的单测**

在 `tests/test_alert_api.py` 末尾追加：

```python
def test_aggregate_active_alerts_merges_by_cell():
    from app.notifier import aggregate_active_alerts
    tasks = [
        {"id": 1, "name": "任务A", "profile_ids": ["siteX"],
         "alert_state": '{"siteX": {"gpt-4": {"s": "alerting", "n": 2}, "gpt-3.5": {"s": "ok", "n": 0}}}'},
        {"id": 2, "name": "任务B", "profile_ids": ["siteX"],
         "alert_state": '{"siteX": {"gpt-4": {"s": "alerting", "n": 3}}}'},
        {"id": 3, "name": "任务C", "profile_ids": ["siteY"],
         "alert_state": '{"siteY": {"claude": {"s": "ok", "n": 0}}}'},
    ]
    out = aggregate_active_alerts(tasks)
    # siteX/gpt-4 被任务A、B同时告警 → 合并成一条，task_count=2，streak取最大
    assert len(out) == 1
    cell = out[0]
    assert cell["profile"] == "siteX" and cell["model"] == "gpt-4"
    assert cell["streak"] == 3
    assert cell["task_count"] == 2
    assert {t["id"] for t in cell["tasks"]} == {1, 2}


def test_aggregate_active_alerts_handles_empty_and_legacy():
    from app.notifier import aggregate_active_alerts
    # 空 alert_state / 裸字符串旧格式 / 缺字段 都不应崩
    tasks = [
        {"id": 1, "name": "x", "profile_ids": ["s"], "alert_state": None},
        {"id": 2, "name": "y", "profile_ids": ["s"], "alert_state": '"ok"'},
        {"id": 3, "name": "z", "profile_ids": ["s"], "alert_state": '{"s": {"m": "alerting"}}'},
    ]
    out = aggregate_active_alerts(tasks)
    # 仅 task3 的裸字符串 "alerting" 计入
    assert len(out) == 1 and out[0]["streak"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_alert_api.py::test_aggregate_active_alerts_merges_by_cell -v`
Expected: FAIL，`ImportError: cannot import name 'aggregate_active_alerts'`

- [ ] **Step 3: 实现纯函数**

在 `app/notifier.py` 的 `_cell_state` 函数之后插入：

```python
def aggregate_active_alerts(tasks: list) -> list:
    """把多个任务的 alert_state 聚合为"当前正在告警"的格子列表，按 (站点,模型) 合并。
    入参 tasks: get_scheduled_tasks() 返回的 dict 列表（含 alert_state/name/id/profile_ids）。
    出参: [{"profile","model","streak","task_count","tasks":[{"id","name"}]}, ...]，
    按 (profile, model) 排序，便于前端稳定渲染。"""
    merged: dict = {}
    for t in tasks:
        states = _load_alert_states(t.get("alert_state"))
        for profile, models in states.items():
            if not isinstance(models, dict):
                continue
            for model, cellval in models.items():
                state, streak = _cell_state(cellval)
                if state != ALERT_ALERTING:
                    continue
                key = (profile, model)
                entry = merged.setdefault(key, {
                    "profile": profile, "model": model,
                    "streak": 0, "tasks": [],
                })
                entry["streak"] = max(entry["streak"], streak)
                entry["tasks"].append({"id": t.get("id"), "name": t.get("name", "")})
    out = []
    for (profile, model), entry in sorted(merged.items()):
        entry["task_count"] = len(entry["tasks"])
        out.append(entry)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_alert_api.py::test_aggregate_active_alerts_merges_by_cell tests/test_alert_api.py::test_aggregate_active_alerts_handles_empty_and_legacy -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/notifier.py tests/test_alert_api.py
git commit -m "feat(notifier): aggregate_active_alerts 按站点×模型合并当前告警 (#76)"
```

---

## Task 2：`GET /api/alerts/active` 端点（后端）

复用 Task 1 的纯函数，按当前用户拉任务、聚合、返回。

**Files:**
- Modify: `app/server.py`（在 `list_schedules`（约 `:2050`）之后插入）
- Test: `tests/test_alert_api.py`

- [ ] **Step 1: 写失败的接口测试**

在 `tests/test_alert_api.py` 追加（沿用文件内现有 `client`/`auth_headers`/`_make_profile`/`_make_notifier` 范式）：

```python
@pytest.mark.asyncio
async def test_active_alerts_endpoint(client):
    from app.db import update_scheduled_task
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 90,
    }, headers=headers)
    sid = resp.json()["id"]
    # 手动写入一个正在告警的格子状态
    await update_scheduled_task(sid, alert_state='{"s": {"gpt-4o-mini": {"s": "alerting", "n": 2}}}')

    r = await client.get("/api/alerts/active", headers=headers)
    assert r.status_code == 200
    alerts = r.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["profile"] == "s" and alerts[0]["model"] == "gpt-4o-mini"
    assert alerts[0]["task_count"] == 1


@pytest.mark.asyncio
async def test_active_alerts_empty_when_none(client):
    headers = await auth_headers(client)
    r = await client.get("/api/alerts/active", headers=headers)
    assert r.status_code == 200 and r.json()["alerts"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_alert_api.py::test_active_alerts_endpoint -v`
Expected: FAIL（404 Not Found，端点未定义）

- [ ] **Step 3: 实现端点**

在 `app/server.py` 的 `list_schedules` 函数之后插入：

```python
@app.get("/api/alerts/active")
async def active_alerts(user: dict = Depends(get_current_user)):
    """监控总览"当前告警区"用：返回当前正在告警的 (站点×模型) 合并列表。"""
    from app.db import get_scheduled_tasks
    from app.notifier import aggregate_active_alerts
    tasks = await get_scheduled_tasks(user["user_id"])
    return {"alerts": aggregate_active_alerts(tasks)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_alert_api.py::test_active_alerts_endpoint tests/test_alert_api.py::test_active_alerts_empty_when_none -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/server.py tests/test_alert_api.py
git commit -m "feat(server): GET /api/alerts/active 当前告警聚合端点 (#76)"
```

---

## Task 3：results 查询性能护栏（后端）

`get_cell_availability_series`（`app/db.py:880`）会把时间窗内该用户全部 results 行捞进 Python 分桶。作为默认首页主数据源前，先确保 `(user_id, timestamp)` 有联合索引，避免重演 #25/PR27 的全表扫描。（窗口收窄在前端 Task 7 处理。）

**Files:**
- Modify: `app/db.py`（建表/初始化处）

- [ ] **Step 1: 确认是否已有索引**

Run: `grep -n "CREATE INDEX\|idx_results" app/db.py`
Expected: 查看 results 表已有哪些索引；若已存在 `(user_id, timestamp)` 联合索引则跳过本 Task 并记录。

- [ ] **Step 2: 在 schema 初始化处加索引**

在 `app/db.py` 创建 `results` 表/索引的初始化代码块（`init_db`/`CREATE TABLE results` 邻近）追加幂等索引：

```python
await conn.execute(text(
    "CREATE INDEX IF NOT EXISTS idx_results_user_ts ON results (user_id, timestamp)"
))
```

放在与其它 `CREATE INDEX IF NOT EXISTS` 相同的位置，保持风格一致。

- [ ] **Step 3: 跑相关测试确认无回归**

Run: `pytest tests/test_alert_api.py -v`
Expected: 全部 passed（建表初始化在测试 fixture 中执行，新索引不应报错）

- [ ] **Step 4: 提交**

```bash
git add app/db.py
git commit -m "perf(db): results 加 (user_id, timestamp) 索引，护栏可用性查询 (#76)"
```

---

## Task 4：飞书卡片加跳转链接（后端）

`build_feishu_card`（`app/notifier.py:82`）当前无任何链接。补一个指向站点的按钮，手机端一键定位。链接基址从配置 `APP_PUBLIC_URL` 读取，未配置则不加链接（保持向后兼容）。

**Files:**
- Modify: `app/config.py`
- Modify: `app/notifier.py`（`build_feishu_card`）
- Test: `tests/test_notifier.py`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_notifier.py` 追加：

```python
def test_feishu_card_includes_link_when_base_url_given():
    from app.notifier import build_feishu_card
    card = build_feishu_card("alert", "任务A", [("siteX", "gpt-4", 0.0)],
                             90, "2026-06-14 10:00:00", base_url="https://app.aitokenperf.com")
    blob = json.dumps(card, ensure_ascii=False)
    assert "https://app.aitokenperf.com/sites/siteX" in blob


def test_feishu_card_no_link_when_base_url_absent():
    from app.notifier import build_feishu_card
    card = build_feishu_card("alert", "任务A", [("siteX", "gpt-4", 0.0)],
                             90, "2026-06-14 10:00:00")
    blob = json.dumps(card, ensure_ascii=False)
    assert "/sites/" not in blob
```

（`tests/test_notifier.py` 顶部若未 `import json` 则补上。）

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_notifier.py::test_feishu_card_includes_link_when_base_url_given -v`
Expected: FAIL（`build_feishu_card` 不接受 `base_url` 参数 → TypeError）

- [ ] **Step 3: 实现**

`app/config.py` 增加（与现有配置项同风格，通常是 `os.environ.get`）：

```python
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")
```

`app/notifier.py` 修改 `build_feishu_card` 签名与 hr 之前的元素拼装：

```python
def build_feishu_card(kind: str, task_name: str,
                      cells: list, threshold: int, ts: str,
                      base_url: str = "") -> dict:
```

在 `elements.append({"tag": "hr"})` 之前插入（仅当有 base_url 且有 cells）：

```python
    if base_url and cells:
        from urllib.parse import quote
        site = quote(str(cells[0][0]), safe="")
        elements.append({"tag": "action", "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "进站点查看 →"},
            "type": "primary",
            "url": f"{base_url}/sites/{site}",
        }]})
```

- [ ] **Step 4: 让调用方传入 base_url**

`app/scheduler.py` 的 `_maybe_send_alert`（`:269` 与 `:271`）两处 `build_feishu_card(...)` 调用补 `base_url`：

```python
    from app.config import APP_PUBLIC_URL
    if alerts:
        await send_webhook(webhook, build_feishu_card("alert", name, alerts, threshold, ts, base_url=APP_PUBLIC_URL))
    if recovers:
        await send_webhook(webhook, build_feishu_card("recover", name, recovers, threshold, ts, base_url=APP_PUBLIC_URL))
```

（`APP_PUBLIC_URL` 的 import 置于函数内现有 `from app.notifier import ...` 邻近，保持局部 import 风格。）

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_notifier.py -v`
Expected: 全部 passed（含原有用例无回归）

- [ ] **Step 6: 提交**

```bash
git add app/config.py app/notifier.py app/scheduler.py tests/test_notifier.py
git commit -m "feat(notifier): 飞书告警卡片加'进站点'跳转链接 (#76)"
```

---

## Task 5：抽离 `SiteHealthBoard.vue` 组件（前端）

把 `SitesView.vue` 内联的健康看板（模板 `:34-90`、相关脚本函数、看板 CSS `:548-583`）整体抽成独立组件，供 `/sites` 与 `/monitor` 共用。**纯重构，行为不变。**

**组件接口（props in / emits out）：**
- props：`sites`（summary 数组）、`availabilityLut`（对象）、`buckets`（数字，默认 24）、`favorites`（Set）
- emits：`test-site(site)`、`toggle-favorite(name)`

**Files:**
- Create: `frontend/src/components/SiteHealthBoard.vue`
- Modify: `frontend/src/views/SitesView.vue`
- Test: `frontend/src/components/__tests__/SiteHealthBoard.test.js`

- [ ] **Step 1: 写组件冒烟测试（失败）**

`frontend/src/components/__tests__/SiteHealthBoard.test.js`：

```javascript
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import SiteHealthBoard from '../SiteHealthBoard.vue';

const sites = [{
  profile: { name: 'siteX', base_url: 'https://api.x.com', models: ['gpt-4'] },
  health: 'error', last_test_at: '20260614_100000',
}];

describe('SiteHealthBoard', () => {
  it('渲染站点行与健康统计', () => {
    const w = mount(SiteHealthBoard, {
      props: { sites, availabilityLut: {}, buckets: 24, favorites: new Set() },
      global: { stubs: { 'router-link': true } },
    });
    expect(w.text()).toContain('siteX');
    expect(w.text()).toContain('异常 1');
  });

  it('点一键测试时 emit test-site', async () => {
    const w = mount(SiteHealthBoard, {
      props: { sites, availabilityLut: {}, buckets: 24, favorites: new Set() },
      global: { stubs: { 'router-link': true } },
    });
    await w.find('.row-actions .btn-ghost').trigger('click');
    expect(w.emitted('test-site')).toBeTruthy();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && bun run test -- SiteHealthBoard`
Expected: FAIL（`SiteHealthBoard.vue` 不存在）

- [ ] **Step 3: 创建组件**

`frontend/src/components/SiteHealthBoard.vue`：把 SitesView 的 `<div class="board-wrap">…</div>`（含 `.health-bar` 与 `<table class="board">`，原 `:34-90`）作为模板根；脚本搬入这些函数与其依赖：`healthCounts`、`siteSeries`、`siteRate`、`siteAvg`、`modelRows`、`expanded`/`toggleExpand`/`isExpanded`、`sortKey`/`sortDir`/`setSort`/`sortArrow`/`sortValue`、`filteredSites`→改为直接用 `props.sites`（排序逻辑保留但作用于 props）、`relativeTime`、`latencyColorStyle`、`rateClass`、`BUCKETS`→用 `props.buckets`、`isFavorite`→`props.favorites.has(name)`。收藏与测试改为 emit：

```vue
<script setup>
import { ref, computed } from 'vue';
import { fmtTime, fmtPct, fmtNum } from '../utils/formatters';
import { getModelMetrics, sparklinePoints, latencyTrendColor, availabilityClass, siteAvgSeries, seriesAvg } from '../utils/siteMetrics';

const props = defineProps({
  sites: { type: Array, default: () => [] },
  availabilityLut: { type: Object, default: () => ({}) },
  buckets: { type: Number, default: 24 },
  favorites: { type: Object, default: () => new Set() },
});
const emit = defineEmits(['test-site', 'toggle-favorite']);
const BUCKETS = computed(() => props.buckets);
function isFavorite(name) { return props.favorites.has(name); }
// …（其余函数原样搬入，凡用 sites.value 处改 props.sites，favorites.value 改 props.favorites）
</script>
```

模板内 `@click="testSite(site)"` → `@click="emit('test-site', site)"`；`@click.stop="toggleFavorite(...)"` → `@click.stop="emit('toggle-favorite', site.profile.name)"`；`goDetail` 用的 `router-link` 保留（组件内 import `useRouter` 或直接用 `<router-link>`）。把原 `:548-583` 的 `.avail-bars`/`table.board`/`.health-bar` 等 CSS 搬入本组件 `<style scoped>`。

- [ ] **Step 4: SitesView 改用组件**

`SitesView.vue`：把模板 `:34-90` 整块替换为：

```vue
<SiteHealthBoard
  :sites="filteredSites"
  :availability-lut="availabilityLut"
  :buckets="BUCKETS"
  :favorites="favorites"
  @test-site="testSite"
  @toggle-favorite="toggleFavorite"
/>
```

删除已搬走的脚本函数与 CSS（保留 `filteredSites` 的筛选/排序入口、`favorites`、`testSite`/`confirmTest`、`loadData`、新建弹窗等 SitesView 仍需的部分）。`import SiteHealthBoard from '../components/SiteHealthBoard.vue'`。

> 注：`filteredSites` 的"筛选"留在 SitesView（搜索框/状态chip在工具栏），"看板内排序"在组件内——避免双向耦合。若排序需作用于已筛列表，组件接收的 `sites` 即已筛结果，组件内排序对其再排序即可。

- [ ] **Step 5: 跑组件测试 + 现有前端测试**

Run: `cd frontend && bun run test`
Expected: 新 `SiteHealthBoard` 测试 passed；现有 `siteMetrics`/`trendAggregator`/`timeRange` 测试无回归。

- [ ] **Step 6: 构建确认无误**

Run: `cd frontend && bun run build`
Expected: 构建成功，无未使用 import / 语法错误。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/SiteHealthBoard.vue frontend/src/components/__tests__/SiteHealthBoard.test.js frontend/src/views/SitesView.vue
git commit -m "refactor(web): 抽离 SiteHealthBoard 组件供站点/监控总览共用 (#76)"
```

---

## Task 6：`getActiveAlerts` API 封装（前端）

**Files:**
- Modify: `frontend/src/api.js`

- [ ] **Step 1: 加封装**

参照 `api.js` 内现有 `getSitesSummary`/`getCellAvailability` 的写法，新增：

```javascript
export function getActiveAlerts() {
  return api('/api/alerts/active');
}
```

（若现有 helper 用 query 拼接工具，则照同款风格；本端点无参数。）

- [ ] **Step 2: 构建确认**

Run: `cd frontend && bun run build`
Expected: 构建成功。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api.js
git commit -m "feat(web): api.getActiveAlerts 封装当前告警端点 (#76)"
```

---

## Task 7：`MonitorView.vue` 监控总览（前端）

组装四块：①顶部状态条 ②当前告警区 ③健康看板（复用 `SiteHealthBoard`）④任务跑批折叠区。默认时间窗收窄到 6h（性能护栏）。

**Files:**
- Create: `frontend/src/views/MonitorView.vue`

- [ ] **Step 1: 创建页面**

`frontend/src/views/MonitorView.vue`，数据加载复用 `getSitesSummary`/`getCellAvailability`/`getActiveAlerts`/`api('/api/schedules')`，看板复用组件：

```vue
<template>
  <section class="tab-content active">
    <!-- ① 状态条 -->
    <div class="health-bar">
      <span class="hb-pill err"><span class="dot d-error"></span>告警中 {{ alerts.length }}</span>
      <span class="hb-pill ok"><span class="dot d-healthy"></span>健康 {{ healthCounts.healthy }}</span>
      <span class="hb-pill un"><span class="dot d-untested"></span>未测 {{ healthCounts.untested }}</span>
    </div>

    <!-- ② 当前告警区 -->
    <div v-if="alerts.length" class="alert-area">
      <div v-for="a in alerts" :key="a.profile + '/' + a.model" class="alert-card">
        <span class="dot d-error"></span>
        <strong>{{ a.profile }} × {{ a.model }}</strong>
        <span class="alert-meta">连续 {{ a.streak }} 轮 · {{ a.task_count > 1 ? '所属 ' + a.task_count + ' 个任务' : a.tasks[0]?.name }}</span>
        <router-link class="btn btn-sm" :to="`/sites/${encodeURIComponent(a.profile)}`">进站点 →</router-link>
      </div>
    </div>
    <div v-else class="alert-ok">✅ 一切正常</div>

    <!-- ③ 健康看板 -->
    <SiteHealthBoard :sites="sites" :availability-lut="availabilityLut" :buckets="BUCKETS" :favorites="favorites" @test-site="onTestSite" @toggle-favorite="() => {}" />

    <!-- ④ 任务跑批折叠 -->
    <details class="tasks-fold">
      <summary>监控任务跑批状态（{{ schedules.length }}）</summary>
      <table class="board"><tbody>
        <tr v-for="s in schedules" :key="s.id">
          <td>{{ s.name }}</td><td>{{ getSiteName(s) }}</td><td>{{ s.status }}</td>
        </tr>
      </tbody></table>
    </details>
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { useAppStore } from '../stores/app';
import { useTimeRangeStore } from '../stores/timeRange';
import { api, getSitesSummary, getCellAvailability, getActiveAlerts } from '../api';
import { buildAvailabilityLookup } from '../utils/siteMetrics';
import { toast } from '../composables/useToast';
import { useRoute } from 'vue-router';
import SiteHealthBoard from '../components/SiteHealthBoard.vue';

const store = useAppStore();
const route = useRoute();
const timeRangeStore = useTimeRangeStore();
const BUCKETS = 24;
const sites = ref([]);
const availabilityLut = ref({});
const alerts = ref([]);
const schedules = ref([]);
const favorites = ref(new Set());

const healthCounts = computed(() => {
  const c = { error: 0, healthy: 0, untested: 0 };
  for (const s of sites.value) c[s.health] = (c[s.health] || 0) + 1;
  return c;
});
function getSiteName(s) { return (s.profile_ids && s.profile_ids[0]) || '-'; }
function onTestSite() { toast('请进入站点详情发起测试', 'info'); }

async function loadData() {
  try {
    const [summary, avail, al, sch] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }),
      getCellAvailability({ hours: timeRangeStore.hours, buckets: BUCKETS }).catch(() => ({ cells: [] })),
      getActiveAlerts().catch(() => ({ alerts: [] })),
      api('/api/schedules').catch(() => ({ schedules: [] })),
    ]);
    sites.value = summary.summary || [];
    availabilityLut.value = buildAvailabilityLookup(avail.cells || []);
    alerts.value = al.alerts || [];
    schedules.value = sch.schedules || [];
  } catch (e) {
    toast('加载监控总览失败: ' + e.message, 'error');
  }
}

watch(() => route.path, (val) => { if (val === '/monitor') loadData(); }, { immediate: true });
watch(() => timeRangeStore.hours, () => { if (route.path === '/monitor') loadData(); });
store.refreshFn = loadData;
onUnmounted(() => { store.refreshFn = null; });
</script>

<style scoped>
.alert-area { display:flex; flex-direction:column; gap:8px; margin:14px 0; }
.alert-card { display:flex; align-items:center; gap:10px; padding:10px 14px; border:1px solid #f3c2c2; background:#fef6f6; border-radius:8px; }
.alert-meta { color:var(--text-tertiary); font-size:12px; }
.alert-card .btn { margin-left:auto; }
.alert-ok { color:var(--success); padding:12px 0; font-weight:600; }
.tasks-fold { margin-top:18px; }
.tasks-fold summary { cursor:pointer; font-size:13px; color:var(--text-secondary); }
.health-bar { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hb-pill { font-size:12px; font-weight:700; padding:5px 11px; border-radius:999px; display:flex; align-items:center; gap:6px; }
.hb-pill.err { background:#fdecec; color:#c0282d; } .hb-pill.ok { background:#e7f6ec; color:#1a7f43; } .hb-pill.un { background:#eee; color:#777; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot.d-healthy { background:var(--success); } .dot.d-error { background:var(--danger); } .dot.d-untested { background:var(--text-tertiary); }
</style>
```

> 说明：MonitorView 的健康看板"看不操作"，故 `@toggle-favorite` 暂空、`test-site` 给提示回站点。收藏读写仍归 `/sites`（阶段二再统一）。

- [ ] **Step 2: 构建确认**

Run: `cd frontend && bun run build`
Expected: 构建成功。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/MonitorView.vue
git commit -m "feat(web): MonitorView 监控总览页（状态条+告警+看板+任务折叠）(#76)"
```

---

## Task 8：路由与导航切换（前端）

**Files:**
- Modify: `frontend/src/router.js`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 改路由**

`frontend/src/router.js`：

```javascript
    { path: '/', redirect: '/monitor' },
    { path: '/monitor', name: 'monitor', component: () => import('./views/MonitorView.vue') },
    { path: '/sites', name: 'sites', component: () => import('./views/SitesView.vue') },
    // …其余不变…
    { path: '/tasks', redirect: '/monitor' },
```

（删除原 `/tasks` 的 `name: 'tasks'` 组件路由，改为 redirect；`/config` 维持 redirect 到 `/sites`。）

- [ ] **Step 2: 改顶部导航**

`frontend/src/App.vue` 的 `tabs`（约 `:42-47`）：

```javascript
const tabs = [
  { name: '监控总览', path: '/monitor', activeMatch: (p) => p === '/' || p.startsWith('/monitor') },
  { name: '站点管理', path: '/sites', activeMatch: (p) => p.startsWith('/sites') },
  { name: '历史与对比', path: '/history' },
];
```

- [ ] **Step 3: 构建确认**

Run: `cd frontend && bun run build`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/router.js frontend/src/App.vue
git commit -m "feat(web): 导航切换——监控总览为主着陆，/tasks 重定向 (#76)"
```

---

## Task 9：阶段验收（全量回归 + 手测）

- [ ] **Step 1: 后端全量测试**

Run: `pytest tests/test_alert_api.py tests/test_notifier.py tests/test_alert_scheduler.py tests/test_alert_db.py -v`
Expected: 全部 passed

- [ ] **Step 2: 前端测试 + 构建**

Run: `cd frontend && bun run test && bun run build`
Expected: 测试全过、构建成功（pre-push hook 同款检查）

- [ ] **Step 3: 手测清单（启动 dev 后逐项核对）**

- 访问 `/` → 自动落到 `/monitor`，状态条/告警区/健康看板/任务折叠都在。
- 访问 `/tasks` → 自动重定向到 `/monitor`。
- 顶导显示「监控总览 / 站点管理 / 历史与对比」，切换正常。
- `/sites` 健康看板（复用组件）行为与改造前一致：排序、展开、收藏、一键测试。
- 制造一个 alerting 状态（或用既有告警任务）→ `/monitor` 当前告警区出现该格子，点「进站点」跳对应站点。

- [ ] **Step 4: 推分支 + 开 PR**

```bash
git push -u origin feat/issue-76-ia-monitor-first
gh pr create --title "feat(web): IA 重构阶段一 — 监控总览主着陆 + 告警聚合端点 (#76)" --body "Closes #76（阶段一；阶段2-4另开 PR）

实现 spec 阶段 1a+1b：
- 后端 aggregate_active_alerts + GET /api/alerts/active
- results (user_id,timestamp) 索引护栏
- 飞书卡片加进站点链接（APP_PUBLIC_URL）
- 抽离 SiteHealthBoard 组件
- MonitorView 监控总览页
- 路由/导航切换，/tasks→/monitor 重定向"
```

> 注：本计划是 spec 5 阶段中的第 1 个。阶段 2（站点列表瘦身 + tab 重排）、阶段 3（新建合一）、阶段 4（模型归并）在本阶段 PR 合并后再分别写计划。

---

## 自检结论（plan 对 spec 的覆盖）

- spec §6 当前告警区 → Task 1/2/7 ✅；健康看板复用组件 → Task 5/7 ✅
- spec §11 告警聚合端点（必做）→ Task 2 ✅；可用性查询护栏 → Task 3 ✅；飞书卡片加链接 → Task 4 ✅
- spec §5 路由：`/`→`/monitor`、`/tasks`→`/monitor` → Task 8 ✅
- spec §15 阶段 1a（抽组件/告警端点/性能）+ 1b（MonitorView/重定向/卡片链接）→ Task 1-8 ✅
- **本阶段不含**：站点列表瘦身、tab 重排、新建内联勾选、模型归并（阶段 2-4，spec §7/§9/§10）——已在 Task 9 备注。
- 类型一致性：`aggregate_active_alerts` 出参字段（profile/model/streak/task_count/tasks）在 Task 1 定义、Task 2 端点透传、Task 7 前端消费，命名一致 ✅
