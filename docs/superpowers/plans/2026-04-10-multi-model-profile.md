# 多模型 Profile 实现计划 (TDD)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造 Profile，使其支持绑定多个模型（同一个 url+key 下测试多个模型），手动测试和定时任务自动展开为多个 BenchTask。

**Architecture:** Profile 的 `model` 字段从单字符串改为 JSON 数组存储。调度层（`start_bench`、`scheduler._run_scheduled_task`）在最外层把多模型 Profile 展开为多个独立 BenchTask，每个 task 的 config.model 仍是单个字符串。底层代码（client.py、protocols/、stats.py）完全不改。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy (async), SQLite (aiosqlite), pytest + pytest-asyncio + httpx

---

## 文件结构

| 文件 | 角色 |
|------|------|
| `app/db.py` | Profile CRUD — model 读写改为 JSON 列表，读取时兼容旧格式 |
| `app/server.py` | `start_bench` 展开多模型、Profile API 改为 models 字段 |
| `app/scheduler.py` | `_run_scheduled_task` 遍历 profile.models 展开任务 |
| `tests/conftest.py` | 共享 fixture（从 test_auth_admin.py 提取） |
| `tests/test_multi_model_profile.py` | 多模型 Profile 的后端集成测试 |
| `frontend/src/views/ProfileView.vue` | model 输入改为 tag 多选（单独任务） |
| `frontend/src/views/TestView.vue` | 展示多模型信息（单独任务） |

---

## Task 0: 提取共享测试 fixture

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_auth_admin.py`

当前 `test_auth_admin.py` 内联了 `event_loop`、`setup_db`、`client` 三个 fixture。提取到 `conftest.py` 以便复用。

- [ ] **Step 1: 创建 conftest.py**

```python
"""共享测试 fixture"""

import os
import tempfile

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# 必须在 import app 之前设置环境变量
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir}/test.db"
os.environ["LOG_MODE"] = "stdout"
os.environ["JWT_SECRET"] = "test-secret-key"

import asyncio  # noqa: E402

from app.server import app  # noqa: E402
from app.db import init_db, engine  # noqa: E402
from app.migrate import migrate  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """每个测试前重新初始化数据库"""
    async with engine.begin() as conn:
        from sqlalchemy import text
        for table in ["scheduled_tasks", "user_settings", "results", "profiles", "sessions", "users"]:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    await init_db()
    await migrate()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


DEFAULT_EMAIL = "admin@example.com"
DEFAULT_PASSWORD = "AITokenPerf#123"


async def login_and_get_token(client, email=DEFAULT_EMAIL, password=DEFAULT_PASSWORD):
    """登录并返回 Bearer token"""
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


async def auth_headers(client):
    """返回带认证的 headers"""
    token = await login_and_get_token(client)
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: 从 test_auth_admin.py 中删除已提取的 fixture**

删除 `test_auth_admin.py` 中的 `event_loop`、`setup_db`、`client` fixture 和相关的 import/os.environ 设置。保留测试函数不变。

- [ ] **Step 3: 运行 test_auth_admin.py 确认提取没有破坏测试**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_auth_admin.py -v
```

Expected: 所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_auth_admin.py
git commit -m "test: 提取共享 fixture 到 conftest.py"
```

---

## Task 1: db.py — Profile model 字段改为 JSON 列表 + 兼容旧格式

**Files:**
- Modify: `app/db.py:357-384` (upsert_profile)
- Modify: `app/db.py:335-354` (get_profiles, get_active_profile)

- [ ] **Step 1: 编写失败测试 — upsert 多模型后读取应返回列表**

```python
# tests/test_multi_model_profile.py
"""TDD 测试：多模型 Profile"""

import json
import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_upsert_profile_with_multiple_models(client):
    """upsert 一个包含多个模型的 profile，读取时应返回列表"""
    headers = await auth_headers(client)

    # 创建多模型 profile
    resp = await client.post("/api/profiles/save", json={
        "name": "test-multi",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
        "provider": "anthropic",
    }, headers=headers)
    assert resp.status_code == 200

    # 读取 profiles 列表
    resp = await client.get("/api/profiles", headers=headers)
    assert resp.status_code == 200
    profiles = resp.json()["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["models"] == ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_multi_model_profile.py::test_upsert_profile_with_multiple_models -v
```

Expected: FAIL — 接口仍然接受 `model`(string)，返回中没有 `models` 字段

- [ ] **Step 3: 修改 upsert_profile 支持 models 列表**

在 `app/db.py` 中修改 `upsert_profile`：

```python
async def upsert_profile(user_id: int, name: str, base_url: str = "", api_key: str = "",
                          api_version: str = "2023-06-01", models: list = None,
                          model: str = "",  # 向后兼容
                          provider: str = "", protocol: str = "",
                          set_active: bool = True):
    # 向后兼容：如果传了 model 字符串，包装为列表
    if models is None and model:
        models = [model]
    elif models is None:
        models = []
    # 存储为 JSON 字符串
    model_json = json.dumps(models)
    # ... (其余 INSERT/UPDATE 逻辑不变，但 model 参数改为 model_json)
```

- [ ] **Step 4: 修改 get_profiles / get_active_profile 返回时解析 models**

在 `app/db.py` 的 `get_profiles` 和 `get_active_profile` 返回结果后，添加兼容处理：

```python
async def get_profiles(user_id: int) -> list[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM profiles WHERE user_id=:uid ORDER BY created_at DESC"), {"uid": user_id}
        )
        rows = _rows_to_dicts(cur.fetchall())
    for row in rows:
        _normalize_profile_models(row)
    return rows


def _normalize_profile_models(p: dict):
    """将旧格式 model 字符串转为 models 列表，同时保留 model 字段向后兼容"""
    raw = p.get("model", "")
    if isinstance(raw, str) and raw.startswith("["):
        try:
            p["models"] = json.loads(raw)
        except json.JSONDecodeError:
            p["models"] = [raw] if raw else []
    elif raw:
        p["models"] = [raw]
    else:
        p["models"] = []
    # 保留 model 字段为第一个模型（向后兼容）
    p["model"] = p["models"][0] if p["models"] else ""
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_multi_model_profile.py::test_upsert_profile_with_multiple_models -v
```

Expected: PASS

- [ ] **Step 6: 添加边界测试**

```python
@pytest.mark.asyncio
async def test_upsert_profile_single_model_backward_compat(client):
    """旧格式 model 字符串应自动包装为单元素列表"""
    headers = await auth_headers(client)
    resp = await client.post("/api/profiles/save", json={
        "name": "test-single",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "model": "gpt-4o",
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    assert profiles[0]["models"] == ["gpt-4o"]
    assert profiles[0]["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_upsert_profile_empty_models(client):
    """空 models 应返回空列表"""
    headers = await auth_headers(client)
    resp = await client.post("/api/profiles/save", json={
        "name": "test-empty",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": [],
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    assert profiles[0]["models"] == []
    assert profiles[0]["model"] == ""


@pytest.mark.asyncio
async def test_update_profile_models(client):
    """更新 profile 的 models 列表"""
    headers = await auth_headers(client)
    # 创建
    await client.post("/api/profiles/save", json={
        "name": "test-update",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a"],
        "provider": "openai",
    }, headers=headers)
    # 更新
    resp = await client.put("/api/profiles/test-update", json={
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a", "model-b", "model-c"],
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    assert profiles[0]["models"] == ["model-a", "model-b", "model-c"]
```

- [ ] **Step 7: 运行所有新增测试**

```bash
python -m pytest tests/test_multi_model_profile.py -v
```

Expected: 全部 PASS

- [ ] **Step 8: 确认旧测试没被破坏**

```bash
python -m pytest tests/test_auth_admin.py -v
```

Expected: 全部 PASS

- [ ] **Step 9: Commit**

```bash
git add app/db.py tests/test_multi_model_profile.py
git commit -m "feat: Profile model 字段改为 JSON 列表存储，向后兼容旧格式"
```

---

## Task 2: server.py — Profile API 适配 models 字段

**Files:**
- Modify: `app/server.py:633-642` (GET /api/profiles 返回 models)
- Modify: `app/server.py:651-674` (POST /api/profiles/save 接受 models)
- Modify: `app/server.py:703-724` (PUT /api/profiles/{name} 接受 models)
- Modify: `app/server.py:677-700` (POST /api/profiles/switch 返回 models)

- [ ] **Step 1: 编写失败测试 — API 返回包含 models 字段**

```python
@pytest.mark.asyncio
async def test_profile_api_returns_models_field(client):
    """Profile API 返回应包含 models 数组和 model 兼容字段"""
    headers = await auth_headers(client)
    await client.post("/api/profiles/save", json={
        "name": "api-test",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.get("/api/profiles", headers=headers)
    p = resp.json()["profiles"][0]
    assert "models" in p
    assert p["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert p["model"] == "gpt-4o"  # 向后兼容


@pytest.mark.asyncio
async def test_switch_profile_returns_models(client):
    """切换 profile 返回的 config 应包含 models"""
    headers = await auth_headers(client)
    await client.post("/api/profiles/save", json={
        "name": "switch-test",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6"],
        "provider": "anthropic",
    }, headers=headers)

    resp = await client.post("/api/profiles/switch", json={"name": "switch-test"}, headers=headers)
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config.get("models") == ["claude-opus-4-6", "claude-sonnet-4-6"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_multi_model_profile.py::test_profile_api_returns_models_field -v
```

Expected: FAIL

- [ ] **Step 3: 修改 server.py 的 save_profile 接受 models 参数**

在 `save_profile`（第 651 行）中，将 `model` 参数替换为 `models`：

```python
@app.post("/api/profiles/save")
async def save_profile(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "Profile name is required"}, status_code=400)

    api_key = data.get("api_key", "")
    if api_key.startswith("..."):
        active = await get_active_profile(user_id)
        api_key = active.get("api_key", "") if active else ""

    # 支持 models 列表和旧的 model 字符串
    models = data.get("models")
    model = data.get("model", "")

    await upsert_profile(
        user_id, name,
        base_url=data.get("base_url", ""),
        api_key=api_key,
        api_version=data.get("api_version", "2023-06-01"),
        models=models,
        model=model,
        provider=data.get("provider", ""),
        protocol=data.get("protocol", ""),
        set_active=True,
    )
    return {"status": "ok"}
```

同理修改 `update_profile`（第 703 行）。

- [ ] **Step 4: 修改 switch_profile 返回 config 中包含 models**

在 `switch_profile`（第 677 行）的 resolved config 构建中，确保 `models` 被包含：

```python
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                resolved[k] = active[k]
        resolved["profile_name"] = active["name"]
        resolved["models"] = active.get("models", [])  # 新增
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_multi_model_profile.py -v
```

Expected: PASS

- [ ] **Step 6: 运行全量测试**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add app/server.py tests/test_multi_model_profile.py
git commit -m "feat: Profile API 适配 models 字段"
```

---

## Task 3: server.py — start_bench 展开多模型为多个 BenchTask

**Files:**
- Modify: `app/server.py:773-829` (start_bench)

- [ ] **Step 1: 编写失败测试 — 多模型 Profile 启动多个 BenchTask**

```python
@pytest.mark.asyncio
async def test_start_bench_expands_multi_model(client):
    """多模型 Profile 启动 bench 应为每个模型创建独立 task"""
    headers = await auth_headers(client)

    # 创建多模型 profile
    await client.post("/api/profiles/save", json={
        "name": "bench-multi",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a", "model-b"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.post("/api/bench/start", json={
        "concurrency_levels": [1],
        "max_tokens": 16,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert len(data["task_ids"]) == 2  # 应创建 2 个 task

    # 停止所有任务
    await client.post("/api/bench/stop", headers=headers)


@pytest.mark.asyncio
async def test_start_bench_single_model_still_works(client):
    """单模型 Profile 启动 bench 应只创建 1 个 task（向后兼容）"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "bench-single",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.post("/api/bench/start", json={
        "concurrency_levels": [1],
        "max_tokens": 16,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert len(data["task_ids"]) == 1

    await client.post("/api/bench/stop", headers=headers)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_multi_model_profile.py::test_start_bench_expands_multi_model -v
```

Expected: FAIL — 返回只有 1 个 task_id（当前只创建单个 task）

- [ ] **Step 3: 修改 start_bench 展开多模型**

将 `start_bench` 中创建单个 BenchTask 的逻辑改为遍历 models 列表：

```python
@app.post("/api/bench/start")
async def start_bench(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]

    existing = manager.get_user_running_task(user_id)
    if existing:
        return JSONResponse({"error": "Benchmark already running"}, status_code=409)

    body = await request.json() if (await request.body()) else {}

    # 输入校验 (不变)
    # ...

    benchmark = await get_settings(user_id)
    active = await get_active_profile(user_id)
    config = dict(benchmark) if benchmark else {}
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                config[k] = active[k]
    _apply_env_overrides(config)

    for key in BENCHMARK_KEYS + CONNECTION_KEYS + ("requests_per_level",):
        if key in body and body[key] is not None:
            if key == "api_key" and isinstance(body[key], str) and body[key].startswith("..."):
                continue
            config[key] = body[key]

    # 获取模型列表
    models = []
    if active and active.get("models"):
        models = active["models"]
    elif config.get("model"):
        models = [config["model"]]
    else:
        return JSONResponse({"error": "No model configured"}, status_code=400)

    # 多模型展开
    if len(models) == 1:
        # 单模型：保持原有行为，返回单个 task_id
        task_id = uuid.uuid4().hex[:12]
        profile_name = active["name"] if active else ""
        task = manager.create_task(task_id, user_id, profile_name=profile_name)
        task.status = "running"
        task.stop_event = asyncio.Event()
        task.start_time = time.monotonic()
        task.asyncio_task = asyncio.create_task(_run_benchmark_task(config, user_id, task))
        return {"status": "started", "task_id": task_id}
    else:
        # 多模型：为每个模型创建独立 task
        group_id = f"multi_{uuid.uuid4().hex[:12]}"
        task_ids = []
        for model_name in models:
            model_config = dict(config)
            model_config["model"] = model_name
            from app.protocols import detect_protocol
            model_config["protocol"] = detect_protocol(model_name, config.get("provider", ""))

            task_id = uuid.uuid4().hex[:12]
            profile_name = active["name"] if active else ""
            task = manager.create_task(task_id, user_id, profile_name=profile_name, group_id=group_id)
            task.model_name = model_name
            task.status = "running"
            task.stop_event = asyncio.Event()
            task.start_time = time.monotonic()
            task.asyncio_task = asyncio.create_task(_run_benchmark_task(model_config, user_id, task))
            task_ids.append(task_id)

        return {"status": "started", "group_id": group_id, "task_ids": task_ids}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_multi_model_profile.py -v
```

Expected: PASS

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/server.py tests/test_multi_model_profile.py
git commit -m "feat: start_bench 展开多模型 Profile 为多个 BenchTask"
```

---

## Task 4: scheduler.py — 定时任务展开多模型

**Files:**
- Modify: `app/scheduler.py:237-283` (profile 遍历循环)

- [ ] **Step 1: 编写失败测试 — 定时任务对多模型 Profile 展开执行**

```python
@pytest.mark.asyncio
async def test_scheduled_task_expands_multi_model(client):
    """定时任务对多模型 Profile 应为每个模型创建子任务"""
    from app.db import create_scheduled_task, get_scheduled_tasks
    from app.scheduler import _run_scheduled_task
    from unittest.mock import patch, AsyncMock

    headers = await auth_headers(client)

    # 创建多模型 profile
    await client.post("/api/profiles/save", json={
        "name": "sched-multi",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a", "model-b", "model-c"],
        "provider": "openai",
    }, headers=headers)

    # 创建定时任务
    task_id = await create_scheduled_task(
        user_id=1,
        name="test-schedule",
        profile_ids=["sched-multi"],
        configs_json={},
        schedule_type="interval",
        schedule_value="1h",
    )

    # mock _run_benchmark_task 避免实际发送请求
    with patch("app.scheduler._run_benchmark_task", new_callable=AsyncMock) as mock_run:
        # 由于 _run_scheduled_task 内部 import _run_benchmark_task，
        # 需要在 server 模块也 mock
        with patch("app.server._run_benchmark_task", new_callable=AsyncMock):
            await _run_scheduled_task(task_id)

    # 验证 _run_benchmark_task 被调用了 3 次（每个模型一次）
    assert mock_run.call_count == 3

    # 验证每次调用的 config 中 model 不同
    models_called = [call.args[0]["model"] for call in mock_run.call_args_list]
    assert sorted(models_called) == ["model-a", "model-b", "model-c"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_multi_model_profile.py::test_scheduled_task_expands_multi_model -v
```

Expected: FAIL — `_run_benchmark_task` 只被调用 1 次（当前每个 profile 只创建 1 个 task）

- [ ] **Step 3: 修改 scheduler.py 的 profile 遍历循环**

在 `_run_scheduled_task` 的第 237-283 行，将"遍历 profile → 创建 1 个 task"改为"遍历 profile → 遍历 models → 每个 model 创建 1 个 task"：

```python
    for pname in profile_ids:
        profile = profile_map.get(pname)
        if not profile:
            # ... (警告逻辑不变)
            continue

        config = dict(benchmark) if benchmark else {}
        for k in CONNECTION_KEYS:
            if profile.get(k):
                config[k] = profile[k]
        _apply_env_overrides(config)

        # 获取模型列表
        models = profile.get("models", [])
        if not models:
            raw_model = profile.get("model", "")
            models = [raw_model] if raw_model else []

        # 应用 configs_json 覆盖
        for key, val in configs_json.items():
            if val is not None:
                config[key] = val

        # concurrency_levels 解析 (不变)
        cl = config.get("concurrency_levels", [100])
        # ... (解析逻辑不变)

        # 为每个模型创建独立 task
        for model_name in models:
            model_config = dict(config)
            model_config["model"] = model_name

            # 检查必要配置
            missing = [k for k in ("base_url", "api_key", "model") if not model_config.get(k)]
            if missing:
                log.warning("定时任务 #%d: profile '%s' model '%s' 缺少配置 %s，跳过",
                           task_id, pname, model_name, missing)
                continue

            from app.protocols import detect_protocol
            model_config["protocol"] = detect_protocol(model_name, model_config.get("provider", ""))

            tid = uuid.uuid4().hex[:12]
            bt = manager.create_task(tid, user_id, profile_name=pname, group_id=group_id)
            bt.scheduled_task_id = task_id
            bt.model_name = model_name
            bt.status = "running"
            bt.stop_event = asyncio.Event()
            bt.start_time = time.monotonic()
            bt.asyncio_task = asyncio.create_task(_run_benchmark_task(model_config, user_id, bt))
            bench_tasks.append(bt)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_multi_model_profile.py::test_scheduled_task_expands_multi_model -v
```

Expected: PASS

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/scheduler.py tests/test_multi_model_profile.py
git commit -m "feat: 定时任务展开多模型 Profile 为多个子任务"
```

---

## Task 5: 前端 — ProfileView model 输入改为 tag 多选

**Files:**
- Modify: `frontend/src/views/ProfileView.vue`

- [ ] **Step 1: 修改 form 数据结构**

将 `form.model` 改为 `form.models`（数组）：

```js
form = ref({
  base_url: '',
  api_key: '',
  models: [],       // 改为数组
  provider: '',
})
```

- [ ] **Step 2: 修改模型选择器 UI**

将现有的单选 combobox 改为 tag 多选组件：
- 已选模型以 chip/tag 形式展示，每个 tag 带删除按钮
- 下拉列表选择后追加到 `form.models` 数组（不重复）
- 支持手动输入自定义模型 ID 后回车添加
- `canSaveProfile` 校验改为 `form.models.length > 0`

- [ ] **Step 3: 修改 loadProfiles 适配新格式**

```js
form.models = p.models || (p.model ? [p.model] : [])
```

- [ ] **Step 4: 修改 saveProfile 发送 models**

```js
await api('/api/profiles/save', {
  method: 'POST',
  body: JSON.stringify({
    name: profileDraftName.value,
    base_url: form.base_url,
    api_key: form.api_key,
    models: form.models,
    provider: form.provider,
  })
})
```

- [ ] **Step 5: 修改 checkProfileDirty 和 snapshotProfileConfig**

```js
function snapshotProfileConfig() {
  savedProfileConfig.value = {
    base_url: form.base_url,
    api_key: form.api_key,
    models: [...form.models],
    provider: form.provider,
  }
}

function checkProfileDirty() {
  if (!savedProfileConfig.value) { profileDirty.value = false; return }
  const s = savedProfileConfig.value
  profileDirty.value =
    form.base_url !== s.base_url ||
    form.api_key !== s.api_key ||
    JSON.stringify(form.models) !== JSON.stringify(s.models) ||
    form.provider !== s.provider
}
```

- [ ] **Step 6: 浏览器中手动验证**

- 创建新 Profile，添加多个模型，保存
- 刷新页面，验证模型列表正确恢复
- 编辑 Profile，增删模型，验证脏检查和保存
- 单模型 Profile 向后兼容显示

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/ProfileView.vue
git commit -m "feat: ProfileView model 输入改为 tag 多选"
```

---

## Task 6: 前端 — TestView 适配多模型展示

**Files:**
- Modify: `frontend/src/views/TestView.vue`

- [ ] **Step 1: 修改 profile 模型展示**

选中 Profile 后展示多模型信息：

```html
<span>模型: {{ (currentProfile?.models || []).join(', ') }}</span>
```

- [ ] **Step 2: 修改 getProfileConfig**

```js
function getProfileConfig() {
  if (!currentProfile.value) return null
  return {
    base_url: currentProfile.value.base_url,
    api_key: currentProfile.value.api_key,
    models: currentProfile.value.models || [],
    provider: currentProfile.value.provider,
  }
}
```

- [ ] **Step 3: startBench 调用不需要改**

因为 `start_bench` 后端接口已经处理了多模型展开，前端只需要调一次接口即可。

- [ ] **Step 4: 浏览器中手动验证**

- 选择多模型 Profile，点击开始测试
- 验证进度条区域显示多个任务（每个模型一个）
- 验证历史结果中每条记录的 model 正确

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TestView.vue
git commit -m "feat: TestView 适配多模型 Profile 展示"
```

---

## Task 7: start_multi_model_bench 接口兼容处理

**Files:**
- Modify: `app/server.py:942-1001` (start_multi_model_bench)

此接口目前从前端 body 接收 `models` 列表，独立于 Profile 的 model 字段。现在 Profile 本身已支持多模型，此接口应优先使用前端传入的 models，但如果没传则回退到 Profile 的 models。

- [ ] **Step 1: 编写测试**

```python
@pytest.mark.asyncio
async def test_multi_model_bench_uses_profile_models(client):
    """start-multi-model 未传 models 时应回退到 Profile 的 models"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "fallback-test",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-x", "model-y"],
        "provider": "openai",
    }, headers=headers)

    # 不传 models，应该使用 profile 的 models
    resp = await client.post("/api/bench/start-multi-model", json={
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["task_ids"]) == 2

    # 停止
    await client.post("/api/bench/stop", headers=headers)
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 修改 start_multi_model_bench 添加回退逻辑**

```python
    models = body.get("models", [])
    if not models:
        # 回退到 Profile 的 models
        models = active.get("models", [])
    if not models or len(models) > 10:
        return JSONResponse({"error": "models 数量需在 1-10 之间"}, status_code=400)
```

- [ ] **Step 4: 运行测试确认通过**

- [ ] **Step 5: 运行全量后端测试**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/server.py tests/test_multi_model_profile.py
git commit -m "feat: start_multi_model_bench 支持回退到 Profile models"
```

---

## 验证清单

完成后运行以下检查：

- [ ] `python -m pytest tests/ -v` — 全部 PASS
- [ ] `python -m pytest tests/test_multi_model_profile.py -v` — 多模型专项测试全部 PASS
- [ ] 浏览器中创建多模型 Profile → 保存 → 刷新验证
- [ ] 浏览器中选多模型 Profile 开始测试 → 验证多个 task 并行
- [ ] 浏览器中定时任务选择多模型 Profile → 手动触发 → 验证多模型展开
- [ ] 旧的单模型 Profile 行为不变（向后兼容）
