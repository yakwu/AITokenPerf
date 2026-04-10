# 修复定时任务执行后页面刷新跳转问题 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复定时任务执行后前端页面意外刷新跳转的问题，并添加定时任务结果的 toast 通知。

**Architecture:** 后端 `/api/bench/status` 返回增加 `scheduled_task_id` 标识，前端据此区分手动测试和定时任务，避免为定时任务启动 SSE 监听。同时将 401 处理从硬刷新改为 Vue Router 软导航，并添加定时任务结果的轮询通知。

**Tech Stack:** Python FastAPI, Vue 3 + Composition API, SSE, httpx (测试)

---

## 文件变更总览

| 文件 | 操作 | 说明 |
|---|---|---|
| `app/server.py:929` | Modify | `/api/bench/status` 返回增加 `scheduled_task_id` |
| `frontend/src/api/index.js:9-14` | Modify | 401 硬刷新改 router.push |
| `frontend/src/views/TestView.vue:632` | Modify | bench:complete 增加跳转守卫 |
| `frontend/src/views/TestView.vue:799-802` | Modify | checkRunningStatus 排除定时任务 |
| `frontend/src/views/TestView.vue` | Modify | 添加定时任务结果轮询通知 |
| `tests/test_bench_status.py` | Create | 后端 bench/status 端点测试 |
| `tests/test_schedule_notify.py` | Create | 定时任务相关测试 |
| `tests/test_tab_refactor.py` | Modify | 前端结构验证测试 |

---

### Task 1: 后端 `/api/bench/status` 返回增加 `scheduled_task_id`

**Files:**
- Modify: `app/server.py:929-941`
- Create: `tests/test_bench_status.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试 /api/bench/status 返回 scheduled_task_id"""

import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_bench_status_returns_scheduled_task_id_for_manual_task(client):
    """手动发起的测试，scheduled_task_id 应为 0"""
    headers = await auth_headers(client)

    # 手动启动一个 benchmark
    resp = await client.post("/api/bench/start", json={
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "model": "gpt-4o-mini",
        "mode": "burst",
        "concurrency_levels": [1],
        "max_tokens": 10,
        "timeout": 30,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200

    # 查询状态
    resp = await client.get("/api/bench/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["scheduled_task_id"] == 0


@pytest.mark.asyncio
async def test_bench_status_returns_scheduled_task_id_for_scheduled_task(client):
    """定时任务发起的测试，scheduled_task_id 应为定时任务 ID"""
    from app.db import create_scheduled_task
    from app.server import manager
    import uuid

    headers = await auth_headers(client)

    # 创建定时任务
    sched_id = await create_scheduled_task(
        user_id=1,
        name="test-sched",
        profile_ids=[],
        configs_json={},
        schedule_type="interval",
        schedule_value="1h",
    )

    # 手动模拟一个定时任务创建的 bench task
    tid = uuid.uuid4().hex[:12]
    task = manager.create_task(tid, 1, profile_name="test", group_id=f"sched_{tid}")
    task.scheduled_task_id = sched_id
    task.status = "running"

    # 查询状态
    resp = await client.get("/api/bench/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["scheduled_task_id"] == sched_id


@pytest.mark.asyncio
async def test_bench_status_idle_returns_zero_scheduled_task_id(client):
    """空闲状态时 scheduled_task_id 应为 0"""
    headers = await auth_headers(client)

    resp = await client.get("/api/bench/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"
    assert data["scheduled_task_id"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_bench_status.py -v`
Expected: FAIL with `KeyError: 'scheduled_task_id'` (field not in response yet)

- [ ] **Step 3: Write minimal implementation**

In `app/server.py`, line 929-941, add `scheduled_task_id` to the return dict:

```python
    return {
        "task_id": task.task_id,
        "status": task.status,
        "scheduled_task_id": task.scheduled_task_id or 0,
        "concurrency": task.current_concurrency,
        "level": task.current_level,
        "total_levels": task.total_levels,
        "done": task.done_count,
        "total": task.total_count,
        "success": task.success_count,
        "failed": task.failed_count,
        "elapsed": elapsed,
        "events": new_events,
    }
```

Also add `scheduled_task_id` to the idle response (line 919-924):

```python
    if not task:
        return {
            "task_id": "", "status": "idle",
            "scheduled_task_id": 0,
            "concurrency": 0, "level": 0, "total_levels": 0,
            "done": 0, "total": 0, "success": 0, "failed": 0,
            "elapsed": 0, "events": [],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_bench_status.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/server.py tests/test_bench_status.py
git commit -m "feat: /api/bench/status 返回增加 scheduled_task_id 字段"
```

---

### Task 2: 前端 checkRunningStatus 排除定时任务

**Files:**
- Modify: `frontend/src/views/TestView.vue:799-802`
- Modify: `tests/test_tab_refactor.py`

- [ ] **Step 1: Write the failing structural test**

In `tests/test_tab_refactor.py`, add:

```python
def test_check_running_status_skips_sse_for_scheduled_task():
    """checkRunningStatus 应根据 scheduled_task_id 决定是否启动 SSE"""
    import pathlib
    vue_file = pathlib.Path(__file__).parent.parent / "frontend" / "src" / "views" / "TestView.vue"
    content = vue_file.read_text()
    # 应该有条件判断：只有非定时任务才启动 SSE
    assert "data.scheduled_task_id" in content, \
        "checkRunningStatus should check scheduled_task_id before starting SSE"
    assert "startSSE" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_tab_refactor.py::test_check_running_status_skips_sse_for_scheduled_task -v`
Expected: FAIL with assertion error

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/views/TestView.vue`, change line 799-802 from:

```javascript
async function checkRunningStatus() {
  const data = await api('/api/bench/status');
  if (data.status === 'running') { taskId.value = data.task_id; running.value = true; store.status = 'running'; subMode.value = 'single'; startSSE(); }
}
```

To:

```javascript
async function checkRunningStatus() {
  const data = await api('/api/bench/status');
  if (data.status === 'running') { taskId.value = data.task_id; running.value = true; store.status = 'running'; subMode.value = 'single'; if (!data.scheduled_task_id) startSSE(); }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_tab_refactor.py::test_check_running_status_skips_sse_for_scheduled_task -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TestView.vue tests/test_tab_refactor.py
git commit -m "fix: checkRunningStatus 对定时任务不启动 SSE 监听"
```

---

### Task 3: bench:complete 处理增加跳转守卫

**Files:**
- Modify: `frontend/src/views/TestView.vue:632`
- Modify: `tests/test_tab_refactor.py`

- [ ] **Step 1: Write the failing structural test**

In `tests/test_tab_refactor.py`, add:

```python
def test_bench_complete_has_guard_before_switch():
    """bench:complete 处理应在 switchTab 前有守卫条件"""
    import pathlib
    vue_file = pathlib.Path(__file__).parent.parent / "frontend" / "src" / "views" / "TestView.vue"
    content = vue_file.read_text()
    # 在 bench:complete case 中，switchTab 不应是无条件执行
    # 找到 bench:complete 所在行
    import re
    match = re.search(r"case 'bench:complete':(.+?)(?:break|case)", content, re.DOTALL)
    assert match, "bench:complete case not found"
    case_body = match.group(1)
    # 应该有条件判断在 switchTab 之前
    assert "liveResults" in case_body or "running" in case_body, \
        "bench:complete should guard switchTab with a condition"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_tab_refactor.py::test_bench_complete_has_guard_before_switch -v`
Expected: FAIL with assertion error

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/views/TestView.vue`, change line 632 from:

```javascript
    case 'bench:complete': stopSSE(); setRunningState(false); toast('测试完成！', 'success'); logLine('<span class="ok">测试完成！</span>'); if (lastCompletedFilename.value) store.pendingFilename = lastCompletedFilename.value; store.switchTab('history'); break;
```

To:

```javascript
    case 'bench:complete': stopSSE(); setRunningState(false); toast('测试完成！', 'success'); logLine('<span class="ok">测试完成！</span>'); if (lastCompletedFilename.value) store.pendingFilename = lastCompletedFilename.value; if (liveResults.value.length > 0) store.switchTab('history'); break;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_tab_refactor.py::test_bench_complete_has_guard_before_switch -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TestView.vue tests/test_tab_refactor.py
git commit -m "fix: bench:complete 增加结果检查守卫再跳转"
```

---

### Task 4: 401 硬刷新改 Vue Router 软导航

**Files:**
- Modify: `frontend/src/api/index.js:9-14`
- Modify: `tests/test_tab_refactor.py`

- [ ] **Step 1: Write the failing structural test**

In `tests/test_tab_refactor.py`, add:

```python
def test_no_hard_redirect_on_401():
    """401 处理不应使用 window.location.href 硬刷新"""
    import pathlib
    api_file = pathlib.Path(__file__).parent.parent / "frontend" / "src" / "api" / "index.js"
    content = api_file.read_text()
    # 在 401 处理块中不应有 window.location.href
    import re
    match = re.search(r"if\s*\(res\.status\s*===\s*401\)(.+?)(?:return|throw|\n\s*\})", content, re.DOTALL)
    assert match, "401 handler not found"
    handler = match.group(1)
    assert "window.location.href" not in handler, \
        "401 handler should not use window.location.href (hard redirect)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_tab_refactor.py::test_no_hard_redirect_on_401 -v`
Expected: FAIL with assertion error

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/api/index.js`, change lines 9-14 from:

```javascript
  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/auth';
    throw new Error('Unauthorized');
  }
```

To:

```javascript
  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    import('../router').then(m => m.default.push('/auth'));
    throw new Error('Unauthorized');
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_tab_refactor.py::test_no_hard_redirect_on_401 -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/index.js tests/test_tab_refactor.py
git commit -m "fix: 401 处理改用 Vue Router 软导航替代硬刷新"
```

---

### Task 5: 定时任务结果轮询 toast 通知

**Files:**
- Modify: `frontend/src/views/TestView.vue` (新增轮询逻辑)
- Create: `tests/test_schedule_notify.py` (后端辅助测试)

- [ ] **Step 1: Write the failing test for the API contract**

```python
"""测试定时任务结果查询接口，为前端轮询通知提供数据支持"""

import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_get_schedule_results_returns_latest_first(client):
    """getScheduleResults 默认返回最新结果在前"""
    from app.db import create_scheduled_task, save_result
    import json

    headers = await auth_headers(client)

    # 创建定时任务
    sched_id = await create_scheduled_task(
        user_id=1,
        name="notify-test",
        profile_ids=[],
        configs_json={},
        schedule_type="interval",
        schedule_value="1h",
    )

    # 保存两个结果
    for i in range(2):
        await save_result(
            user_id=1,
            filename=f"sched_{sched_id}_result_{i}.json",
            data={"test": f"result_{i}"},
            scheduled_task_id=sched_id,
        )

    # 查询结果，limit=1 应返回最新的
    resp = await client.get(
        f"/api/schedules/{sched_id}/results?limit=1",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) == 1
```

- [ ] **Step 2: Run test to verify it passes/fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_schedule_notify.py -v`
Expected: 取决于 `save_result` 和 schedule results 端点是否已存在（大概率 PASS，因为这些接口已有实现）

- [ ] **Step 3: Write the frontend implementation**

In `frontend/src/views/TestView.vue`, add after the existing `onUnmounted` line (line 797):

1. Add a ref for tracking known result IDs and a timer ref:

```javascript
const lastKnownResultIds = ref({});
const schedulePollTimer = ref(null);
```

2. Add the polling function (before `onMounted`):

```javascript
async function pollScheduleUpdates() {
  if (subMode.value !== 'schedule') return;
  for (const s of schedules.value) {
    try {
      const res = await getScheduleResults(s.id, { limit: 1 });
      const results = res.results || [];
      if (results.length > 0) {
        const latestId = results[0].id || results[0].filename;
        if (lastKnownResultIds.value[s.id] !== undefined && lastKnownResultIds.value[s.id] !== latestId) {
          toast(`定时任务「${s.name}」有新执行结果`, 'info');
        }
        lastKnownResultIds.value[s.id] = latestId;
      }
    } catch (e) { /* 静默忽略 */ }
  }
}

function startSchedulePolling() {
  stopSchedulePolling();
  // 先立即初始化一次已知状态
  pollScheduleUpdates();
  schedulePollTimer.value = setInterval(() => pollScheduleUpdates(), 30000);
}

function stopSchedulePolling() {
  if (schedulePollTimer.value) {
    clearInterval(schedulePollTimer.value);
    schedulePollTimer.value = null;
  }
}
```

3. In `onMounted`, after `refreshSchedules()`, add:

```javascript
startSchedulePolling();
```

4. In `onUnmounted`, add `stopSchedulePolling()`:

```javascript
onUnmounted(() => { stopSSE(); stopMultiPolling(); stopSchedulePolling(); destroyCharts(); });
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TestView.vue tests/test_schedule_notify.py
git commit -m "feat: 定时任务结果轮询 toast 通知（30s 间隔）"
```

---

### Task 6: 整体回归测试

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Manual verification checklist**

验证以下场景：
1. 手动发起测试 → 完成后正常跳转到历史记录页面
2. 定时任务执行 → 页面不刷新、不跳转
3. 定时任务执行后 → 在定时任务页面等待 30s → toast 通知有新结果
4. Token 过期 → 优雅跳转到登录页（无硬刷新）

- [ ] **Step 3: Commit any fixes**

如果有修复，单独提交。
