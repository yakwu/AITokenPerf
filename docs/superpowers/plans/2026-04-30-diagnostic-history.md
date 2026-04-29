# 诊断历史回看功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 HistoryView 页面新增「诊断历史」Tab，支持筛选、分页、展开查看历史诊断详情

**Architecture:** 后端重写列表查询（摘要列 + COUNT + 筛选），新增 filter-options 级联端点；前端从 SiteTestTab 提取 DiagnosticCard.vue 共享组件，在 HistoryView 新增诊断历史 Tab

**Tech Stack:** Python/FastAPI/SQLAlchemy (后端), Vue 3 Composition API (前端), pytest (测试)

---

## 文件结构

| 文件 | 角色 |
|------|------|
| `app/db.py:1481-1493` | 重写 `list_channel_diagnostics()`，新增 `list_diagnostic_filter_options()` |
| `app/server.py:1061-1069` | 改造列表端点，新增 filter-options 端点 |
| `frontend/src/api/index.js:76-79` | 更新 `listChannelDiagnostics()`，新增 `getDiagnosticFilterOptions()` |
| `frontend/src/components/DiagnosticCard.vue` | **新建**，从 SiteTestTab 提取的共享诊断详情卡片 |
| `frontend/src/components/SiteTestTab.vue:169-282` | 改用 DiagnosticCard 组件 |
| `frontend/src/views/HistoryView.vue` | 新增诊断历史 Tab、筛选栏、列表、展开详情 |
| `tests/test_channel_diagnostics_db.py` | 新增筛选、COUNT、filter_options 测试 |
| `tests/test_channel_diagnostics_api.py` | 新增列表筛选、total/has_more、filter-options 测试 |

---

### Task 1: 重写 `list_channel_diagnostics()` — 摘要列 + 筛选 + COUNT

**Files:**
- Modify: `app/db.py:1481-1493`
- Test: `tests/test_channel_diagnostics_db.py`

- [ ] **Step 1: 写失败测试 — 列表只返回摘要列，不含 report_json**

```python
# tests/test_channel_diagnostics_db.py 追加：

@pytest.mark.asyncio
async def test_list_channel_diagnostics_summary_only(client):
    """列表查询不返回 report_json"""
    from app.db import save_channel_diagnostic, list_channel_diagnostics

    await save_channel_diagnostic(
        user_id=1, profile_name="p1", model="m1",
        status="passed", overall_risk="low", confidence=0.8,
        report_json={"prompt_cache": {"status": "supported"}},
    )

    items, total = await list_channel_diagnostics(user_id=1)
    assert total == 1
    assert "report_json" not in items[0]
    assert items[0]["profile_name"] == "p1"
    assert items[0]["model"] == "m1"
    assert items[0]["status"] == "passed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_channel_diagnostics_db.py::test_list_channel_diagnostics_summary_only -v`
Expected: FAIL — `list_channel_diagnostics()` 返回的是 `list[dict]` 不是 tuple，且包含 `report_json`

- [ ] **Step 3: 实现 — 重写 `list_channel_diagnostics()`**

```python
# app/db.py 替换 1481-1493 行：

_LIST_DIAG_COLS = "id, profile_name, model, status, overall_risk, confidence, created_at"


async def list_channel_diagnostics(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    profile_name: str | None = None,
    model: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    """按用户列出诊断记录（摘要），返回 (items, total)"""
    where = ["user_id = :uid"]
    params: dict = {"uid": user_id, "limit": limit, "offset": offset}
    if profile_name:
        where.append("profile_name = :pn")
        params["pn"] = profile_name
    if model:
        where.append("model = :model")
        params["model"] = model
    if status:
        where.append("status = :status")
        params["status"] = status
    where_sql = " AND ".join(where)

    async with engine.begin() as conn:
        count_row = await conn.execute(
            text(f"SELECT COUNT(*) FROM channel_diagnostics WHERE {where_sql}"),
            params,
        )
        total = count_row.fetchone()[0]

        rows = await conn.execute(
            text(f"""
                SELECT {_LIST_DIAG_COLS} FROM channel_diagnostics
                WHERE {where_sql}
                ORDER BY id DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        items = [dict(r._mapping) for r in rows.fetchall()]

    return items, total
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_channel_diagnostics_db.py -v`
Expected: ALL PASS

- [ ] **Step 5: 修复已有测试 `test_list_channel_diagnostics` 的返回值解构**

```python
# tests/test_channel_diagnostics_db.py 修改 test_list_channel_diagnostics：

@pytest.mark.asyncio
async def test_list_channel_diagnostics(client):
    """按用户列出诊断记录"""
    from app.db import save_channel_diagnostic, list_channel_diagnostics

    for i in range(3):
        await save_channel_diagnostic(
            user_id=1,
            profile_name=f"profile-{i}",
            model="claude-opus-4-6",
            status="passed",
            overall_risk="low",
            confidence=0.8,
            report_json={"schema_version": 1},
        )

    items, total = await list_channel_diagnostics(user_id=1, limit=10)
    assert total == 3
    assert len(items) == 3
    assert items[0]["profile_name"] == "profile-2"  # 最新在前
```

- [ ] **Step 6: 运行全部 DB 测试确认通过**

Run: `pytest tests/test_channel_diagnostics_db.py -v`
Expected: ALL PASS

- [ ] **Step 7: 提交**

```bash
git add app/db.py tests/test_channel_diagnostics_db.py
git commit -m "feat: 重写 list_channel_diagnostics 支持摘要列、筛选和 COUNT"
```

---

### Task 2: 新增 `list_diagnostic_filter_options()` — 级联筛选选项

**Files:**
- Modify: `app/db.py` (追加到 1493 行之后)
- Test: `tests/test_channel_diagnostics_db.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_channel_diagnostics_db.py 追加：

@pytest.mark.asyncio
async def test_list_diagnostic_filter_options(client):
    """返回去重的筛选选项，支持级联"""
    from app.db import save_channel_diagnostic, list_diagnostic_filter_options

    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m1", status="passed", overall_risk="low", confidence=0.8, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m2", status="warning", overall_risk="medium", confidence=0.5, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-b", model="m1", status="passed", overall_risk="low", confidence=0.9, report_json={})
    await save_channel_diagnostic(user_id=999, profile_name="other", model="m3", status="passed", overall_risk="low", confidence=0.5, report_json={})

    # 无筛选 — 返回当前用户的全部去重值
    opts = await list_diagnostic_filter_options(user_id=1)
    assert sorted(opts["profile_names"]) == ["site-a", "site-b"]
    assert sorted(opts["models"]) == ["m1", "m2"]

    # 级联：选了 site-a 后，模型只返回 site-a 下的
    opts = await list_diagnostic_filter_options(user_id=1, profile_name="site-a")
    assert sorted(opts["models"]) == ["m1", "m2"]

    # 级联：选了 site-b 后，模型只有 m1
    opts = await list_diagnostic_filter_options(user_id=1, profile_name="site-b")
    assert opts["models"] == ["m1"]

    # 用户隔离
    opts = await list_diagnostic_filter_options(user_id=999)
    assert opts["profile_names"] == ["other"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_channel_diagnostics_db.py::test_list_diagnostic_filter_options -v`
Expected: FAIL — `list_diagnostic_filter_options` 不存在

- [ ] **Step 3: 实现**

```python
# app/db.py 追加到 list_channel_diagnostics 之后：

async def list_diagnostic_filter_options(
    user_id: int,
    profile_name: str | None = None,
    model: str | None = None,
    status: str | None = None,
) -> dict:
    """返回级联筛选后的去重选项"""
    where = ["user_id = :uid"]
    params: dict = {"uid": user_id}
    if profile_name:
        where.append("profile_name = :pn")
        params["pn"] = profile_name
    if model:
        where.append("model = :model")
        params["model"] = model
    if status:
        where.append("status = :status")
        params["status"] = status
    where_sql = " AND ".join(where)

    async with engine.begin() as conn:
        rows = await conn.execute(
            text(f"""
                SELECT DISTINCT profile_name FROM channel_diagnostics
                WHERE {where_sql} ORDER BY profile_name
            """),
            params,
        )
        profile_names = [r[0] for r in rows.fetchall()]

        rows = await conn.execute(
            text(f"""
                SELECT DISTINCT model FROM channel_diagnostics
                WHERE {where_sql} ORDER BY model
            """),
            params,
        )
        models = [r[0] for r in rows.fetchall()]

    return {"profile_names": profile_names, "models": models}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_channel_diagnostics_db.py -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add app/db.py tests/test_channel_diagnostics_db.py
git commit -m "feat: 新增 list_diagnostic_filter_options 级联筛选"
```

---

### Task 3: 改造列表 API 端点 — 筛选参数 + total/has_more

**Files:**
- Modify: `app/server.py:1061-1069`
- Test: `tests/test_channel_diagnostics_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_channel_diagnostics_api.py 追加：

@pytest.mark.asyncio
async def test_list_channel_diagnostics_with_filters(client):
    """列表端点支持筛选参数，返回 total/has_more"""
    headers = await auth_headers(client)

    # 创建 profile
    await client.post("/api/profiles/save", json={
        "name": "list-test", "base_url": "https://api.anthropic.com",
        "api_key": "sk-test", "api_key_action": "replace",
        "models": ["m1"], "provider": "anthropic",
    }, headers=headers)

    from unittest.mock import AsyncMock, patch
    from app.channel_diagnostics import CacheDiagnosticResult

    mock_result = CacheDiagnosticResult(
        status="passed", overall_risk="low", confidence=0.85,
        probes=[], report={"prompt_cache": {"status": "supported", "hit_rate": 0.8}},
    )

    # 插入 2 条记录
    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        await client.post("/api/channel-diagnostics", json={"profile_name": "list-test", "model": "m1"}, headers=headers)
        mock_result.status = "warning"
        await client.post("/api/channel-diagnostics", json={"profile_name": "list-test", "model": "m1"}, headers=headers)

    # 无筛选
    resp = await client.get("/api/channel-diagnostics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["has_more"] is False
    assert len(data["items"]) == 2

    # 按状态筛选
    resp = await client.get("/api/channel-diagnostics?status=warning", headers=headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "warning"

    # 按模型筛选
    resp = await client.get("/api/channel-diagnostics?model=m1", headers=headers)
    data = resp.json()
    assert data["total"] == 2

    # 分页 has_more
    resp = await client.get("/api/channel-diagnostics?limit=1", headers=headers)
    data = resp.json()
    assert data["total"] == 2
    assert data["has_more"] is True
    assert len(data["items"]) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_channel_diagnostics_api.py::test_list_channel_diagnostics_with_filters -v`
Expected: FAIL — 响应中没有 `has_more` 字段

- [ ] **Step 3: 实现 — 改造 server.py 列表端点**

```python
# app/server.py 替换 1061-1069 行：

@app.get("/api/channel-diagnostics")
async def list_channel_diagnostics_handler(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    profile_name: str | None = Query(None),
    model: str | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """列出诊断记录"""
    items, total = await list_channel_diagnostics(
        user["user_id"], limit=limit, offset=offset,
        profile_name=profile_name, model=model, status=status,
    )
    return {"items": items, "total": total, "has_more": offset + limit < total}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_channel_diagnostics_api.py -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add app/server.py tests/test_channel_diagnostics_api.py
git commit -m "feat: 列表端点支持筛选参数和 total/has_more"
```

---

### Task 4: 新增 filter-options API 端点

**Files:**
- Modify: `app/server.py` (追加到列表端点之后)
- Test: `tests/test_channel_diagnostics_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_channel_diagnostics_api.py 追加：

@pytest.mark.asyncio
async def test_filter_options_endpoint(client):
    """filter-options 端点返回级联筛选选项"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "fo-test", "base_url": "https://api.anthropic.com",
        "api_key": "sk-test", "api_key_action": "replace",
        "models": ["m1"], "provider": "anthropic",
    }, headers=headers)

    from unittest.mock import AsyncMock, patch
    from app.channel_diagnostics import CacheDiagnosticResult

    mock_result = CacheDiagnosticResult(
        status="passed", overall_risk="low", confidence=0.85,
        probes=[], report={"prompt_cache": {"status": "supported", "hit_rate": 0.8}},
    )

    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        await client.post("/api/channel-diagnostics", json={"profile_name": "fo-test", "model": "m1"}, headers=headers)
        await client.post("/api/channel-diagnostics", json={"profile_name": "fo-test", "model": "m2"}, headers=headers)

    # 无筛选
    resp = await client.get("/api/channel-diagnostics/filter-options", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "m1" in data["models"]
    assert "m2" in data["models"]
    assert "fo-test" in data["profile_names"]

    # 级联：按 profile_name 筛选
    resp = await client.get("/api/channel-diagnostics/filter-options?profile_name=fo-test", headers=headers)
    data = resp.json()
    assert sorted(data["models"]) == ["m1", "m2"]

    # 用户隔离
    resp = await client.get("/api/channel-diagnostics/filter-options", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_channel_diagnostics_api.py::test_filter_options_endpoint -v`
Expected: FAIL — 404 Not Found

- [ ] **Step 3: 实现 — 新增 filter-options 端点**

```python
# app/server.py 在列表端点之后追加：

@app.get("/api/channel-diagnostics/filter-options")
async def diagnostic_filter_options_handler(
    profile_name: str | None = Query(None),
    model: str | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """返回级联筛选选项"""
    return await list_diagnostic_filter_options(
        user["user_id"], profile_name=profile_name, model=model, status=status,
    )
```

- [ ] **Step 4: 确保 server.py 顶部导入了新函数**

检查 `app/server.py` 的 db 导入区域，确保 `list_diagnostic_filter_options` 已导入。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_channel_diagnostics_api.py -v`
Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add app/server.py tests/test_channel_diagnostics_api.py
git commit -m "feat: 新增 GET /api/channel-diagnostics/filter-options 端点"
```

---

### Task 5: 前端 API 客户端适配

**Files:**
- Modify: `frontend/src/api/index.js:76-79`

- [ ] **Step 1: 更新 `listChannelDiagnostics` 和新增 `getDiagnosticFilterOptions`**

```javascript
// frontend/src/api/index.js 替换 76-79 行并追加：

export const listChannelDiagnostics = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api('/api/channel-diagnostics' + (qs ? '?' + qs : ''));
};

export const getDiagnosticFilterOptions = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api('/api/channel-diagnostics/filter-options' + (qs ? '?' + qs : ''));
};
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/api/index.js
git commit -m "feat: 前端 API 客户端适配诊断筛选参数和 filter-options"
```

---

### Task 6: 提取 DiagnosticCard.vue 共享组件

**Files:**
- Create: `frontend/src/components/DiagnosticCard.vue`
- Read: `frontend/src/components/SiteTestTab.vue:169-282` (源码参考)

- [ ] **Step 1: 创建 DiagnosticCard.vue**

从 SiteTestTab 的 `.diag-result-card` 区域（第 169-282 行）提取，封装为独立组件。

Props:
- `report` (Object, required) — 完整的 `report_json` 对象，包含 `probes`、`prompt_cache`、`response_cache`、`proxy_cache` 等
- `status` (String) — 诊断状态（passed/warning/no_usage_fields/no_cache/inconclusive/error）
- `overallRisk` (String) — 风险等级
- `confidence` (Number) — 置信度

组件内部包含：
- 状态标签（颜色+文案）— 使用 `diagStatusColor`/`diagStatusLabel`/`diagStatusTooltip` 函数
- 命中率和置信度展示
- 代理缓存警告
- 探针详情列表（可展开/折叠每个 probe 的 raw_usage、request/response preview、token 校验）
- Response cache 警告

组件内部状态：
- `expandedProbes` — Set，控制哪些 probe 已展开

```vue
<!-- frontend/src/components/DiagnosticCard.vue -->
<template>
  <div class="diag-result-card">
    <!-- 状态行 -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span :style="'background:' + statusColor + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
        {{ statusLabel }}
      </span>
      <span v-if="statusTooltip" class="info-tip" :data-tip="statusTooltip">?</span>
    </div>

    <!-- 命中率 + 置信度 -->
    <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary);margin-bottom:8px">
      <span v-if="cacheHitRate != null">命中率: <strong>{{ (cacheHitRate * 100).toFixed(1) }}%</strong></span>
      <span v-if="confidence != null">置信度: <strong>{{ (confidence * 100).toFixed(0) }}%</strong></span>
    </div>

    <!-- 状态说明 -->
    <div v-if="status === 'no_usage_fields'" style="font-size:11px;color:var(--text-tertiary);margin-bottom:8px">
      渠道没有返回缓存相关信息，无法判断缓存是否生效。
    </div>
    <div v-if="status === 'no_cache'" style="font-size:11px;color:var(--warning);margin-bottom:8px">
      渠道返回了缓存字段，但值全是 0 — 可能是发送内容没达到缓存最低长度要求，或渠道本身不支持缓存。
    </div>

    <!-- 代理缓存警告 -->
    <div v-if="report?.proxy_cache?.status === 'detected'" style="font-size:11px;color:var(--warning);margin-bottom:8px;padding:6px 8px;background:var(--warning-bg,#fff8e1);border-radius:4px;border:1px solid var(--warning,#f9a825)">
      这个渠道在中间层做了处理（{{ report.proxy_cache.evidence }}），以下结果测的是渠道的缓存，不是 Claude 的缓存，不具有参考价值。
    </div>

    <!-- 探针详情 -->
    <div v-if="report?.probes?.length" class="diag-probes">
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
              <pre>{{ formatJson(probe.request_preview) }}</pre>
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

    <!-- Response Cache -->
    <div v-if="report?.response_cache && report.response_cache.status !== 'not_detected'" style="margin-top:6px;font-size:11px;color:var(--warning)">
      检测到响应缓存: {{ report.response_cache.status }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';

const props = defineProps({
  report: { type: Object, required: true },
  status: { type: String, default: '' },
  overallRisk: { type: String, default: '' },
  confidence: { type: Number, default: null },
});

const expandedProbes = ref(new Set());

const cacheHitRate = computed(() => {
  return props.report?.prompt_cache?.hit_rate ?? null;
});

const statusColor = computed(() => diagStatusColor(props.status));
const statusLabel = computed(() => diagStatusLabel(props.status));
const statusTooltip = computed(() => diagStatusTooltip(props.status));

function toggleProbe(idx) {
  const s = new Set(expandedProbes.value);
  if (s.has(idx)) s.delete(idx); else s.add(idx);
  expandedProbes.value = s;
}

function formatJson(str) {
  try { return JSON.stringify(JSON.parse(str), null, 2); } catch { return str; }
}

// --- 状态映射 ---
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

// --- 探针映射 ---
function diagProbeLabel(name) {
  const map = { cold_prefix: 'Cold', warm_prefix: 'Warm', breaker_prefix: 'Breaker', repeat_identical: 'Repeat' };
  return map[name] || name;
}

function probeTokenColor(probeName, kind) {
  if (kind === 'read') return 'var(--success)';
  if (kind === 'creation') return 'var(--info)';
  return 'var(--text-tertiary)';
}

function probeTokenCheck(probe) {
  const total = (probe.usage?.input_tokens || 0) + (probe.usage?.cache_creation_input_tokens || 0) + (probe.usage?.cache_read_input_tokens || 0);
  if (probe.expected_total_tokens > 0 && total > probe.expected_total_tokens * 2) {
    return { text: '⚠ 注入', color: 'var(--danger)', tip: '渠道报告的 token 总量远超预估，疑似中间层注入内容' };
  }
  if (probe.expected_total_tokens > 0 && total < probe.expected_total_tokens * 0.3) {
    return { text: '⚠ 丢失', color: 'var(--warning)', tip: '渠道报告的 token 总量远低于预估，疑似内容被截断' };
  }
  return null;
}
</script>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/DiagnosticCard.vue
git commit -m "feat: 提取 DiagnosticCard.vue 共享诊断详情卡片组件"
```

---

### Task 7: SiteTestTab 改用 DiagnosticCard 组件

**Files:**
- Modify: `frontend/src/components/SiteTestTab.vue:169-282`

- [ ] **Step 1: 替换 SiteTestTab 的诊断详情为 DiagnosticCard**

在 `<script setup>` 中导入组件：
```javascript
import DiagnosticCard from './DiagnosticCard.vue';
```

将 `SiteTestTab.vue` 第 169-282 行的 `v-for` 内容替换为：

```vue
<div v-for="model in selectedModels" :key="model" class="diag-result-card" :class="{ 'diag-pending': diagResults[model]?.status === 'pending' }">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
    <span style="font-family:var(--font-mono);font-size:13px;font-weight:600">{{ model }}</span>
    <span v-if="diagResults[model]?.status === 'pending'" style="color:var(--text-tertiary);font-size:11px">等待中</span>
    <span v-else-if="diagResults[model]?.status === 'running'" style="display:flex;align-items:center;gap:6px;color:var(--text-secondary);font-size:11px">
      <span class="result-loading-spinner" style="width:12px;height:12px;border-width:2px"></span>
      诊断中...
    </span>
  </div>
  <DiagnosticCard
    v-if="diagResults[model] && diagResults[model].status !== 'pending' && diagResults[model].status !== 'running'"
    :report="diagResults[model]"
    :status="diagResults[model].status"
    :overall-risk="diagResults[model].overall_risk"
    :confidence="diagResults[model].confidence"
  />
</div>
```

删除 SiteTestTab 中已移入 DiagnosticCard 的函数：`diagStatusColor`、`diagStatusLabel`、`diagStatusTooltip`、`probeTokenCheck`、`probeTokenColor`、`diagProbeLabel`、`toggleRawUsage`。

删除 `expandedRawProbes` ref（已移入 DiagnosticCard 内部）。

- [ ] **Step 2: 验证前端能正常构建**

Run: `cd frontend && bun run build`
Expected: 构建成功，无报错

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/SiteTestTab.vue
git commit -m "refactor: SiteTestTab 改用 DiagnosticCard 共享组件"
```

---

### Task 8: HistoryView 新增诊断历史 Tab

**Files:**
- Modify: `frontend/src/views/HistoryView.vue`

- [ ] **Step 1: 添加 Tab 切换和诊断历史基础结构**

在 HistoryView 的 `<template>` 最顶部（`<section>` 内部第一行）添加 Tab 切换器：

```vue
<div class="tab-switcher" style="margin-bottom:16px">
  <button class="tab-btn" :class="{ active: activeTab === 'bench' }" @click="activeTab = 'bench'">基准测试</button>
  <button class="tab-btn" :class="{ active: activeTab === 'diag' }" @click="activeTab = 'diag'; loadDiagHistory()">诊断历史</button>
</div>
```

将现有基准测试内容包裹在 `<template v-if="activeTab === 'bench'">` 中。

在 `<script setup>` 中添加：
```javascript
import { listChannelDiagnostics, getChannelDiagnostic, getDiagnosticFilterOptions } from '../api/index.js';
import DiagnosticCard from '../components/DiagnosticCard.vue';

const activeTab = ref('bench');

// 诊断历史状态
const diagItems = ref([]);
const diagTotal = ref(0);
const diagOffset = ref(0);
const diagPageSize = 20;
const diagHasMore = computed(() => diagOffset.value + diagPageSize < diagTotal.value);
const diagLoading = ref(false);

// 筛选
const diagFilterProfile = ref('');
const diagFilterModel = ref('');
const diagFilterStatus = ref('');
const diagFilterOptions = ref({ profile_names: [], models: [] });
const diagStatusOptions = ['passed', 'warning', 'no_usage_fields', 'no_cache', 'inconclusive', 'error'];

// 展开详情
const diagExpandedId = ref(null);
const diagDetailCache = ref({});
const diagDetailLoading = ref(false);
const diagDetailError = ref(false);
```

- [ ] **Step 2: 实现诊断历史加载和筛选逻辑**

```javascript
async function loadDiagHistory(reset = true) {
  if (diagLoading.value) return;
  diagLoading.value = true;
  if (reset) {
    diagOffset.value = 0;
    diagExpandedId.value = null;
    diagDetailCache.value = {};
  }
  try {
    const params = { limit: diagPageSize, offset: diagOffset.value };
    if (diagFilterProfile.value) params.profile_name = diagFilterProfile.value;
    if (diagFilterModel.value) params.model = diagFilterModel.value;
    if (diagFilterStatus.value) params.status = diagFilterStatus.value;
    const data = await listChannelDiagnostics(params);
    if (reset) {
      diagItems.value = data.items;
    } else {
      diagItems.value.push(...data.items);
    }
    diagTotal.value = data.total;
  } finally {
    diagLoading.value = false;
  }
}

async function loadDiagFilterOptions() {
  const params = {};
  if (diagFilterProfile.value) params.profile_name = diagFilterProfile.value;
  if (diagFilterModel.value) params.model = diagFilterModel.value;
  if (diagFilterStatus.value) params.status = diagFilterStatus.value;
  diagFilterOptions.value = await getDiagnosticFilterOptions(params);
}

function onDiagFilterChange() {
  loadDiagFilterOptions();
  loadDiagHistory(true);
}

function loadMoreDiag() {
  diagOffset.value += diagPageSize;
  loadDiagHistory(false);
}

async function toggleDiagExpand(id) {
  if (diagExpandedId.value === id) {
    diagExpandedId.value = null;
    return;
  }
  diagExpandedId.value = id;
  if (diagDetailCache.value[id]) return;

  diagDetailLoading.value = true;
  diagDetailError.value = false;
  try {
    const detail = await getChannelDiagnostic(id);
    diagDetailCache.value[id] = detail;
  } catch {
    diagDetailError.value = true;
  } finally {
    diagDetailLoading.value = false;
  }
}

function retryDiagDetail() {
  if (diagExpandedId.value) {
    delete diagDetailCache.value[diagExpandedId.value];
    toggleDiagExpand(diagExpandedId.value);
  }
}
```

- [ ] **Step 3: 实现诊断历史 Tab 模板**

在 `</template>` 前（基准测试内容之后）添加：

```vue
<!-- Diagnostic History Tab -->
<template v-if="activeTab === 'diag'">
  <div class="diag-history">
    <!-- 筛选栏 -->
    <div class="filter-chips" style="margin-bottom:16px">
      <FilterDropdown v-model="diagFilterProfile" :options="diagFilterOptions.profile_names" all-label="全部站点" wide @update:modelValue="onDiagFilterChange" />
      <FilterDropdown v-model="diagFilterModel" :options="diagFilterOptions.models" all-label="全部模型" wide @update:modelValue="onDiagFilterChange" />
      <FilterDropdown v-model="diagFilterStatus" :options="diagStatusOptions" all-label="全部状态" @update:modelValue="onDiagFilterChange" />
    </div>

    <!-- 列表 -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:150px">时间</th>
              <th>站点</th>
              <th>模型</th>
              <th style="width:120px">状态</th>
              <th style="width:80px">置信度</th>
              <th style="width:40px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-if="!diagItems.length && !diagLoading">
              <tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-tertiary)">暂无诊断记录</td></tr>
            </template>
            <template v-for="item in diagItems" :key="item.id">
              <!-- 摘要行 -->
              <tr class="history-row" :class="{ expanded: diagExpandedId === item.id }" style="cursor:pointer" @click="toggleDiagExpand(item.id)">
                <td>{{ fmtTimestamp(item.created_at) }}</td>
                <td>{{ item.profile_name }}</td>
                <td style="font-family:var(--font-mono);font-size:12px">{{ item.model }}</td>
                <td>
                  <span :style="'background:' + diagStatusColor(item.status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
                    {{ diagStatusLabel(item.status) }}
                  </span>
                </td>
                <td>{{ item.confidence != null ? (item.confidence * 100).toFixed(0) + '%' : '-' }}</td>
                <td style="text-align:center;font-size:11px;color:var(--text-tertiary)">{{ diagExpandedId === item.id ? '▲' : '▼' }}</td>
              </tr>
              <!-- 展开详情 -->
              <tr v-if="diagExpandedId === item.id">
                <td colspan="6" style="padding:0">
                  <div style="padding:16px 20px;background:var(--bg-secondary)">
                    <div v-if="diagDetailLoading && !diagDetailCache[item.id]" style="text-align:center;padding:20px;color:var(--text-tertiary)">
                      <span class="result-loading-spinner" style="width:16px;height:16px;border-width:2px;margin-right:8px"></span>
                      加载中...
                    </div>
                    <div v-else-if="diagDetailError && !diagDetailCache[item.id]" style="text-align:center;padding:20px">
                      <span style="color:var(--danger)">加载失败</span>
                      <button class="btn btn-ghost btn-sm" style="margin-left:8px" @click.stop="retryDiagDetail()">重试</button>
                    </div>
                    <DiagnosticCard
                      v-else-if="diagDetailCache[item.id]"
                      :report="diagDetailCache[item.id].report_json"
                      :status="diagDetailCache[item.id].status"
                      :overall-risk="diagDetailCache[item.id].overall_risk"
                      :confidence="diagDetailCache[item.id].confidence"
                    />
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 加载更多 -->
    <div v-if="diagHasMore" style="text-align:center;margin-top:12px">
      <button class="btn btn-ghost" @click="loadMoreDiag()" :disabled="diagLoading">
        {{ diagLoading ? '加载中...' : '加载更多' }}
      </button>
    </div>
  </div>
</template>
```

- [ ] **Step 4: 导入 DiagnosticCard 的状态映射函数**

在 `<script setup>` 中：
```javascript
import DiagnosticCard, { diagStatusColor, diagStatusLabel } from '../components/DiagnosticCard.vue';
```

- [ ] **Step 5: 修复 `diagTooltip()` — 移除 critical，增加 no_cache**

```javascript
// 替换现有的 diagTooltip 函数：
function diagTooltip(r) {
  const statusMap = {
    passed: 'Claude 缓存命中',
    warning: '缓存证据异常',
    inconclusive: '无法判断',
    no_usage_fields: '未返回缓存 usage',
    no_cache: '未达到缓存阈值',
    error: '诊断失败',
  };
  const s = statusMap[r.channel_diagnostic_status] || '未知';
  const rate = r.channel_diagnostic_cache_hit_rate;
  const parts = [`诊断: ${s}`];
  if (rate != null) parts.push(`缓存命中率: ${(rate * 100).toFixed(1)}%`);
  return parts.join(' | ');
}
```

- [ ] **Step 6: 初始化加载 filter options**

在 HistoryView 的 `<script setup>` 中添加 onMounted：
```javascript
onMounted(() => {
  loadDiagFilterOptions();
});
```

确保 `onMounted` 已从 vue 导入。

- [ ] **Step 7: 验证前端构建**

Run: `cd frontend && bun run build`
Expected: 构建成功

- [ ] **Step 8: 提交**

```bash
git add frontend/src/views/HistoryView.vue
git commit -m "feat: HistoryView 新增诊断历史 Tab、筛选栏、展开详情"
```

---

### Task 9: 端到端验证

- [ ] **Step 1: 运行全部后端测试**

Run: `pytest tests/test_channel_diagnostics_db.py tests/test_channel_diagnostics_api.py -v`
Expected: ALL PASS

- [ ] **Step 2: 运行前端构建**

Run: `cd frontend && bun run build`
Expected: 构建成功

- [ ] **Step 3: 提交最终状态**

```bash
git add -A
git commit -m "feat: 诊断历史回看功能完成"
```
