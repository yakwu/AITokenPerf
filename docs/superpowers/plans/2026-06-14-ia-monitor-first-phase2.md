# IA 重构 · 阶段二（站点区瘦身 + 详情 tab 重排）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/sites` 从"完整健康看板"瘦身为"管理清单 + 轻量健康摘要 + 监控三态列"，并把站点详情 tab 重排为 `概况 · 监控 · 单次测试 · 配置`（保留数据感知默认 tab、清理 `?tab=trends` 别名）。

**Architecture:** 后端 `get_sites_summary` 为每站点补 `monitor_status`（active/paused/none，基于已加载的 scheduled_tasks，零新查询）。前端 `/sites` 不再复用完整的 `SiteHealthBoard`（那个继续服务 `/monitor`），改为一个轻量管理清单；站点详情 `internalTabs` 重排+改名。

**Tech Stack:** 后端 FastAPI + SQLAlchemy(async) + pytest；前端 Vue 3 `<script setup>` + Vitest。包管理 **bun**。后端本机测试用 `python3.11 -m pytest`，前端 `cd frontend && ./node_modules/.bin/vitest run` / `bun run build`。

**前置：** 本计划基于 **阶段一已合并**（PR #77）。实现分支从合并后的 main 切 `feat/issue-76-ia-phase2`（或在 #77 之上 stack）。spec：`docs/superpowers/specs/2026-06-14-ia-monitor-first-redesign-design.md` §7/§8/§13。

**张力提示：** 阶段一为复用，`/sites` 暂时仍渲染完整 `SiteHealthBoard`。本阶段按 spec §7 落实瘦身——`/sites` 改为管理清单，`SiteHealthBoard` 仅 `/monitor` 用。`/sites` 的"详细 site×model 大表"能力迁移到 `/monitor`（已在阶段一提供）。

---

## 文件结构

| 文件 | 责任 | 动作 |
|------|------|------|
| `app/db.py` | `get_sites_summary` 每站点补 `monitor_status` | 修改 |
| `tests/test_*` (站点摘要相关) | monitor_status 单测/接口测试 | 修改/新增 |
| `frontend/src/views/SiteDetailView.vue` | `internalTabs` 重排+改名；保留数据感知默认 tab | 修改 |
| `frontend/src/views/SitesView.vue` | `/sites` 改为轻量管理清单（弃用 SiteHealthBoard） | 修改 |
| `frontend/src/components/NotificationCenter.vue` | `?tab=trends` → 规范 tab | 修改 |
| `frontend/src/views/TasksView.vue` | 内部 `?tab=trends` 链接清理（孤儿文件，顺手） | 修改 |
| `frontend/src/components/__tests__/` | SitesView 清单渲染冒烟（视情况） | 可选 |

---

## Task 1：后端 `get_sites_summary` 补 `monitor_status`（每站点监控三态）

`get_sites_summary` 已加载 `scheduled_tasks`（构建 `task_to_profile`）。复用同一份数据，为每站点算出监控态：`active`（至少一个 status=active 的任务引用本站点）/ `paused`（有任务但全 paused）/ `none`（无任务）。

**Files:**
- Modify: `app/db.py`（`get_sites_summary` 内）
- Test: `tests/test_alert_api.py`（沿用 client/auth_headers/_make_profile 范式）或站点摘要相关测试文件

- [ ] **Step 1: 写失败的接口测试**

在 `tests/test_alert_api.py`（或站点摘要测试文件）追加：

```python
@pytest.mark.asyncio
async def test_sites_summary_monitor_status(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)   # 建站点 "s"
    # 无任务 → none
    r = await client.get("/api/sites/summary", headers=headers)
    entry = next(e for e in r.json()["summary"] if e["profile"]["name"] == "s")
    assert entry["monitor_status"] == "none"
    # 建一个 active 任务 → active
    await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
    }, headers=headers)
    r = await client.get("/api/sites/summary", headers=headers)
    entry = next(e for e in r.json()["summary"] if e["profile"]["name"] == "s")
    assert entry["monitor_status"] == "active"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3.11 -m pytest tests/test_alert_api.py::test_sites_summary_monitor_status -v`
Expected: FAIL（`KeyError: 'monitor_status'`）

- [ ] **Step 3: 实现**

在 `get_sites_summary` 里，构建 `task_to_profile` 的那段之后，加一个"每站点监控态"映射（用 `st.get("status")` 与 `pids[0]`）：

```python
    # 每站点监控态：active 优先，其次 paused，否则 none
    monitor_status = {p["name"]: "none" for p in profiles}
    for st in scheduled_tasks:
        pids = st.get("profile_ids") or []
        if not pids:
            continue
        pname = pids[0]
        if pname not in monitor_status:
            continue
        st_status = st.get("status")
        if st_status == "active":
            monitor_status[pname] = "active"
        elif st_status == "paused" and monitor_status[pname] != "active":
            monitor_status[pname] = "paused"
```

然后在初始化 `summary[key] = {...}` 的字典里加上 `"monitor_status": "none"`，并在返回前（或循环结束后）回填：

```python
    for name, entry in summary.items():
        entry["monitor_status"] = monitor_status.get(name, "none")
```

（放在 `return list(summary.values())` 之前。确认 summary 的 key 是 profile name。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python3.11 -m pytest tests/test_alert_api.py::test_sites_summary_monitor_status -v`
Expected: PASS

- [ ] **Step 5: 回归 + 提交**

Run: `python3.11 -m pytest tests/test_alert_api.py -q`（确认 sites/summary 既有用例无回归）
```bash
git add app/db.py tests/test_alert_api.py
git commit -m "feat(db): sites/summary 每站点补 monitor_status 三态 (#76)"
```

---

## Task 2：站点详情 tab 重排 + 改名（前端）

`SiteDetailView.vue` 的 `internalTabs`（`:105-110`）当前是 `概况/测试/持续监控/设置`，顺序 overview, test, schedule, config。按 spec §8 改为顺序+命名 `概况(overview) · 监控(schedule) · 单次测试(test) · 配置(config)`。**保留数据感知默认 tab**（`:131-135` 的 `hasData ? 'overview' : 'test'`）与 `tabQueryMap`（key 不变，仅顺序/label 变）。

**Files:**
- Modify: `frontend/src/views/SiteDetailView.vue`

- [ ] **Step 1: 改 internalTabs 顺序与 label**

`:105-110` 改为：

```javascript
const internalTabs = [
  { key: 'overview', label: '概况' },
  { key: 'schedule', label: '监控' },
  { key: 'test', label: '单次测试' },
  { key: 'config', label: '配置' },
];
```

- [ ] **Step 2: 确认默认 tab 逻辑不动**

核对 `:131-135` 仍是：
```javascript
    if (!route.query.tab) {
      const hasData = foundSummary?.latest_results?.length > 0;
      activeTab.value = hasData ? 'overview' : 'test';
    }
```
**不要改**（数据感知默认 tab 是阶段一/既有已修好的行为）。`tabQueryMap`（`:113`）keys 不变（overview/test/schedule/config + trends/history→overview），保留。

- [ ] **Step 3: 构建确认**

Run: `cd frontend && bun run build`
Expected: 成功。

- [ ] **Step 4: 手测核对（dev 起站点详情）**

- 进入有数据站点：tab 顺序为 `概况·监控·单次测试·配置`，默认落概况。
- 进入无数据站点：默认落"单次测试"（test）。
- 点"监控"tab → 显示 SiteSchedulesTab（持续监控内容）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/SiteDetailView.vue
git commit -m "feat(web): 站点详情 tab 重排为 概况·监控·单次测试·配置 (#76)"
```

---

## Task 3：清理 `?tab=trends` 别名链接（前端）

`trends` 是历史别名（tabQueryMap 里映射到 overview）。把源头链接改为规范的 `?tab=overview`（或省略 tab，靠数据感知默认）。**保留 tabQueryMap 里的 `trends→overview` 映射**以兼容外部旧链接。

**Files:**
- Modify: `frontend/src/components/NotificationCenter.vue`（`:59`）
- Modify: `frontend/src/views/SitesView.vue`（`:194`、`:255`；注意 `:322` 用的是 `?tab=test`，那是新建后跳测试，**保留不动**）
- Modify: `frontend/src/views/TasksView.vue`（`:60`，孤儿文件，顺手清理）

- [ ] **Step 1: 替换 trends 链接**

把上述位置的 `?tab=trends` 改为 `?tab=overview`：
- `NotificationCenter.vue:59`：`router.push(\`/sites/${encodeURIComponent(n.profileName)}?tab=overview\`)`
- `SitesView.vue:194`：`router.push(\`/sites/${encodeURIComponent(name)}?tab=overview\`)`
- `SitesView.vue:255`：`onClick: () => router.push(\`/sites/${encodeURIComponent(siteName)}?tab=overview\`)`
- `TasksView.vue:60`：`:to="\`/sites/${encodeURIComponent(getSiteName(s))}?tab=overview\`"`

（`SitesView.vue:322` 的 `?tab=test` 是新建站点后跳单次测试，**不改**。注意 SitesView 在 Task 4 会大改，本 Task 若与 Task 4 冲突，可把 SitesView 的两处 trends 清理并入 Task 4 一起做——见 Task 4 备注。）

- [ ] **Step 2: 构建确认**

Run: `cd frontend && bun run build`
Expected: 成功。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/NotificationCenter.vue frontend/src/views/TasksView.vue
git commit -m "refactor(web): 统一站点详情跳转用规范 tab=overview，清理 trends 别名 (#76)"
```

---

## Task 4：`/sites` 瘦身为轻量管理清单（前端）

`SitesView.vue` 当前复用完整 `SiteHealthBoard`。按 spec §7 改为**管理清单**：每行 `站点名 · 目标地址 · 模型数 · 健康摘要(成功率 + 可用性点) · 监控三态 · 进入`。去掉每模型展开的 TTFT/趋势/Token/s 详细列（那些在 `/monitor` 看）。`SiteHealthBoard` 组件本身保留（`/monitor` 仍用），仅 `/sites` 不再用它。

**Files:**
- Modify: `frontend/src/views/SitesView.vue`

设计要点：
- 数据：`loadData` 已拉 `getSitesSummary`（现含 `monitor_status`，Task 1）+ `getCellAvailability`（可用性 LUT）。沿用。
- 每行健康摘要：成功率用现有 `siteRate`（站点可用率柱均值）逻辑；可用性点用 `siteSeries` 的最末几桶或一个紧凑 sparkline（可用现有 `availabilityClass` + 几个柱）。
- 监控列：`entry.monitor_status` → `🟢开`(active) / `⏸暂停`(paused) / `⚪关`(none)。
- 保留：搜索框、状态筛选 chips、`healthCounts` 全量统计条、收藏置顶排序、新建站点弹窗、一键测试确认弹窗。
- 删除：对 `SiteHealthBoard` 的 import 与使用；从阶段一搬到组件、SitesView 不再需要的看板专属逻辑。

- [ ] **Step 1: 写/更新清单渲染冒烟测试（可选但推荐）**

若为 SitesView 加测试成本高（它依赖 store/router/api），可改为对"行渲染所需的纯函数"（如监控态→标签映射）做单测，或跳过组件测试、靠 Task 末手测。决定后在报告说明。最小推荐：抽一个纯函数 `monitorLabel(status)` 返回 `{text,cls}`，给它写单测：

```javascript
// frontend/src/utils/__tests__/siteList.test.js
import { describe, it, expect } from 'vitest';
import { monitorLabel } from '../siteList';
describe('monitorLabel', () => {
  it('三态映射', () => {
    expect(monitorLabel('active').text).toContain('开');
    expect(monitorLabel('paused').text).toContain('暂停');
    expect(monitorLabel('none').text).toContain('关');
  });
});
```
对应 `frontend/src/utils/siteList.js`：
```javascript
export function monitorLabel(status) {
  if (status === 'active') return { text: '🟢 开', cls: 'mon-on' };
  if (status === 'paused') return { text: '⏸ 暂停', cls: 'mon-paused' };
  return { text: '⚪ 关', cls: 'mon-off' };
}
```

- [ ] **Step 2: 跑测试确认失败 → 创建 util → 通过**

Run: `cd frontend && ./node_modules/.bin/vitest run -- siteList`
（先失败，建 `siteList.js` 后通过。）

- [ ] **Step 3: 改 SitesView 模板为管理清单**

把当前 `<SiteHealthBoard .../>` 替换为轻量表格（沿用现有 health-bar 工具栏在上方不动）：

```vue
<table v-else class="manage-list">
  <thead><tr>
    <th>站点</th><th>目标地址</th><th>模型</th><th>健康</th><th>监控</th><th></th>
  </tr></thead>
  <tbody>
    <tr v-for="site in filteredSites" :key="site.profile.name">
      <td>
        <button class="fav" :class="{ on: isFavorite(site.profile.name) }" @click.stop="toggleFavorite(site.profile.name)">★</button>
        <router-link class="sname" :to="`/sites/${encodeURIComponent(site.profile.name)}`">{{ site.profile.name }}</router-link>
      </td>
      <td class="mono">{{ site.profile.base_url }}</td>
      <td>{{ (site.profile.models || []).length }}</td>
      <td>
        <span class="rate" :class="rateClass(siteRate(site))">{{ siteRate(site)!=null ? fmtPct(siteRate(site)) : '未测' }}</span>
        <span class="avail-bars sm"><i v-for="(r,i) in siteSeries(site).slice(-8)" :key="i" :class="'ab-'+availabilityClass(r)"></i></span>
      </td>
      <td><span class="mon" :class="monitorLabel(site.monitor_status).cls">{{ monitorLabel(site.monitor_status).text }}</span></td>
      <td class="row-actions"><button class="btn btn-sm" @click="goDetail(site)">进入 →</button></td>
    </tr>
  </tbody>
</table>
```

脚本相应保留/恢复：`siteRate`、`siteSeries`（基于 availabilityLut，阶段一搬去组件了，这里需在 SitesView 重新引入精简版）、`availabilityClass`/`fmtPct`/`rateClass`、`goDetail`、`monitorLabel`（import 自 util）。删除 `import SiteHealthBoard`。CSS 加 `.manage-list`、`.mon*`、复用 `.avail-bars`（从组件复制必要的几条到 SitesView scoped）。

> 备注：把 Task 3 里 SitesView 的两处 `?tab=trends` 顺手在本 Task 一并清成 `?tab=overview`（goDetail 用 `/sites/:name`，无 tab，靠默认）。

- [ ] **Step 4: 构建 + 测试**

Run: `cd frontend && ./node_modules/.bin/vitest run && bun run build`
Expected: 全绿 + 构建成功。

- [ ] **Step 5: 手测核对**

- `/sites` 显示管理清单：站点名/地址/模型数/健康(成功率+小可用性条)/监控(开/暂停/关)/进入。
- 顶部全量健康统计条仍在；搜索、状态筛选、收藏置顶、新建站点、一键测试仍可用。
- 点"进入"到站点详情；监控态正确反映任务状态。
- `/monitor` 不受影响（仍用完整 SiteHealthBoard）。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/SitesView.vue frontend/src/utils/siteList.js frontend/src/utils/__tests__/siteList.test.js
git commit -m "feat(web): /sites 瘦身为管理清单（健康摘要+监控三态），看板归监控总览 (#76)"
```

---

## Task 5：阶段验收 + PR

- [ ] **Step 1: 后端全量**

Run: `python3.11 -m pytest tests/test_alert_api.py tests/test_notifier.py tests/test_alert_scheduler.py tests/test_alert_db.py -q`
Expected: 全绿

- [ ] **Step 2: 前端测试 + 构建**

Run: `cd frontend && ./node_modules/.bin/vitest run && bun run build`
Expected: 全绿 + 构建成功

- [ ] **Step 3: 手测清单**

- `/sites` 管理清单 + 监控三态正确（建/暂停/删任务后刷新核对）。
- 站点详情 tab 顺序 `概况·监控·单次测试·配置`，数据感知默认 tab 正常。
- 旧链接 `?tab=trends` 仍能打开（映射 overview），新链接用规范 tab。
- `/monitor` 完整看板不受影响。

- [ ] **Step 4: 推分支 + 开 PR**

```bash
git push -u origin feat/issue-76-ia-phase2
gh pr create --title "feat(web): IA 重构阶段二 — /sites 管理清单 + 详情 tab 重排 (#76)" --body "阶段二 · refs #76（阶段三/四另开 PR，不自动关闭）

- 后端 sites/summary 补 monitor_status 三态
- 站点详情 tab 重排为 概况·监控·单次测试·配置（保留数据感知默认 tab）
- 清理 ?tab=trends 别名（保留映射兼容旧链接）
- /sites 瘦身为管理清单（健康摘要+监控三态），完整看板归 /monitor"
```

---

## 自检结论（plan 对 spec 的覆盖）

- spec §7 站点列表瘦身（站点名/地址/模型数/健康摘要/监控三态/进入）→ Task 1（monitor_status）+ Task 4 ✅
- spec §7 监控列三态（active/paused/none）→ Task 1 + Task 4 ✅
- spec §8 tab 重排 `概况·监控·单次测试·配置` + 保留数据感知默认 → Task 2 ✅
- spec §13 清理 `?tab=trends` 别名 + 保留兼容映射 → Task 3（+ Task 4 收尾 SitesView 两处）✅
- **本阶段不含**：新建内联开监控（阶段三 §9）、模型归并（阶段四 §10）。
- 类型一致性：`monitor_status` 值域（active/paused/none）在 Task 1 后端定义、Task 4 前端 `monitorLabel` 消费，一致 ✅
- 依赖：Task 4 依赖 Task 1 的 `monitor_status` 字段；Task 3 与 Task 4 在 SitesView 有重叠（已在 Task 3/4 备注由 Task 4 收尾 SitesView 两处 trends）。
