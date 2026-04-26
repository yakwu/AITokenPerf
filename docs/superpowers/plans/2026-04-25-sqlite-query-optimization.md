# SQLite 高负载查询优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 20 万级 `results` 数据下，所有查询路径稳定可用，消除全表扫描和 Python 端聚合瓶颈。

**Architecture:** 三层优化——(1) 给 `results` 表加索引覆盖主要查询路径；(2) 增加 `profile_name`/`base_url` 冗余列，替代 `json_extract` 过滤；(3) 重写 `get_sites_summary` 和趋势查询为 SQL 聚合。所有改动 SQLite/PG 双模兼容。

**Tech Stack:** Python 3.12, SQLAlchemy (aiosqlite/asyncpg), pytest + pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/db.py` | Modify | Schema、索引、迁移、查询函数 |
| `app/db.py:491-508` | Modify | `save_result` 增加 profile_name/base_url 参数 |
| `app/db.py:552-674` | Modify | `get_results_aggregated` 去掉 json_extract |
| `app/db.py:817-889` | Modify | `get_site_trend` 去掉 json_extract |
| `app/db.py:1178-1270` | Modify | `get_sites_summary` 改 SQL 聚合 |
| `tests/test_sqlite_optimization.py` | Create | 所有优化相关测试 |

---

### Task 1: 给 results 表加索引

**Files:**
- Modify: `app/db.py:210-232` (init_db 函数)
- Create: `tests/test_sqlite_optimization.py`

- [ ] **Step 1: 写失败测试——验证索引存在**

```python
# tests/test_sqlite_optimization.py
"""TDD 测试：SQLite 高负载查询优化"""

import json
import pytest
from datetime import datetime, timedelta

from sqlalchemy import text
from app.db import engine, save_result, get_results_aggregated


async def _get_indexes(table_name: str) -> set[str]:
    """获取表的所有索引名"""
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t"),
            {"t": table_name},
        )
        return {row[0] for row in cur.fetchall()}


@pytest.mark.asyncio
async def test_results_table_has_indexes():
    """results 表应有覆盖主要查询路径的索引"""
    indexes = await _get_indexes("results")
    assert "idx_results_user_time" in indexes, "缺少 (user_id, created_at) 索引"
    assert "idx_results_user_sched_time" in indexes, "缺少 (user_id, scheduled_task_id, created_at) 索引"
    assert "idx_results_filename" in indexes, "缺少 filename 索引"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_results_table_has_indexes -v`
Expected: FAIL — "缺少 (user_id, created_at) 索引"

- [ ] **Step 3: 实现——在 init_db 中加索引**

在 `app/db.py` 的 `init_db()` 函数中，在 `idx_sched_status_next` 索引之后（约 line 232），添加：

```python
        # results 表查询优化索引
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_time ON results (user_id, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_sched_time ON results (user_id, scheduled_task_id, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_filename ON results (user_id, filename)"
        ))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_results_table_has_indexes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: 给 results 表加 user_id/created_at/scheduled_task_id/filename 索引"
```

---

### Task 2: 给 results 表加冗余列 + 迁移

**Files:**
- Modify: `app/db.py:79-93` (_SQLITE_SCHEMA)
- Modify: `app/db.py:157-171` (_PG_SCHEMA)
- Modify: `app/db.py:210-232` (init_db)
- Modify: `tests/test_sqlite_optimization.py`

- [ ] **Step 1: 写失败测试——验证冗余列存在**

在 `tests/test_sqlite_optimization.py` 中追加：

```python
@pytest.mark.asyncio
async def test_results_table_has_redundant_columns():
    """results 表应有 profile_name 和 base_url 冗余列"""
    async with engine.connect() as conn:
        cur = await conn.execute(text("PRAGMA table_info(results)"))
        columns = {row[1] for row in cur.fetchall()}
    assert "profile_name" in columns, "缺少 profile_name 列"
    assert "base_url" in columns, "缺少 base_url 列"


@pytest.mark.asyncio
async def test_redundant_columns_have_indexes():
    """冗余列应有对应索引"""
    indexes = await _get_indexes("results")
    assert "idx_results_user_profile_time" in indexes, "缺少 (user_id, profile_name, created_at) 索引"
    assert "idx_results_user_url_time" in indexes, "缺少 (user_id, base_url, created_at) 索引"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_results_table_has_redundant_columns -v`
Expected: FAIL — "缺少 profile_name 列"

- [ ] **Step 3: 在 Schema 中加列**

在 `_SQLITE_SCHEMA` 的 `results` 表定义（`app/db.py` line 92）`created_at` 行之前，加两行：

```sql
    profile_name   TEXT NOT NULL DEFAULT '',
    base_url       TEXT NOT NULL DEFAULT '',
```

在 `_PG_SCHEMA` 的 `results` 表定义（`app/db.py` line 170 附近）同样位置加：

```sql
    profile_name   TEXT NOT NULL DEFAULT '',
    base_url       TEXT NOT NULL DEFAULT '',
```

- [ ] **Step 4: 在 init_db 中加冗余列迁移 + 索引**

在 `init_db()` 的索引创建代码之后（Task 1 加的索引之后），追加：

```python
        # 冗余列：对已有表 ALTER TABLE（SQLite 3.35+ 支持 ADD COLUMN IF NOT EXISTS）
        if _is_sqlite:
            for col_def in [
                "ALTER TABLE results ADD COLUMN profile_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN base_url TEXT NOT NULL DEFAULT ''",
            ]:
                try:
                    await conn.execute(text(col_def))
                except Exception:
                    pass  # 列已存在则忽略
        else:
            for col_def in [
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS profile_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS base_url TEXT NOT NULL DEFAULT ''",
            ]:
                await conn.execute(text(col_def))

        # 冗余列索引
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_profile_time ON results (user_id, profile_name, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_url_time ON results (user_id, base_url, created_at DESC)"
        ))
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_results_table_has_redundant_columns tests/test_sqlite_optimization.py::test_redundant_columns_have_indexes -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: results 表加 profile_name/base_url 冗余列及索引"
```

---

### Task 3: 冗余列数据回填迁移

**Files:**
- Modify: `app/db.py` (init_db 函数，追加回填逻辑)
- Modify: `tests/test_sqlite_optimization.py`

- [ ] **Step 1: 写失败测试——验证历史数据回填**

在 `tests/test_sqlite_optimization.py` 中追加：

```python
@pytest.mark.asyncio
async def test_backfill_redundant_columns():
    """历史数据的 profile_name/base_url 应从 config_json 回填"""
    # 直接插入一条只有 config_json 没有冗余列值的数据
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO results (user_id, test_id, filename, timestamp,
                config_json, summary_json, percentiles_json,
                profile_name, base_url)
            VALUES (1, 'bf-test', 'bf_test.json', '20260425_120000',
                '{"profile_name":"OldSite","base_url":"https://old.example.com"}',
                '{}', '{}', '', '')
        """))

    # 运行回填迁移
    from app.db import _backfill_redundant_columns
    await _backfill_redundant_columns()

    # 验证回填结果
    async with engine.connect() as conn:
        cur = await conn.execute(text(
            "SELECT profile_name, base_url FROM results WHERE test_id='bf-test'"
        ))
        row = cur.fetchone()
    assert row[0] == "OldSite", f"profile_name 应回填为 OldSite，实际为 {row[0]}"
    assert row[1] == "https://old.example.com", f"base_url 应回填，实际为 {row[1]}"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_backfill_redundant_columns -v`
Expected: FAIL — `ImportError` 或 `_backfill_redundant_columns` 不存在

- [ ] **Step 3: 实现回填函数**

在 `app/db.py` 的 `_migrate_schedule_results_profile_name()` 函数之后（约 line 268），追加：

```python
async def _backfill_redundant_columns():
    """将 config_json 中的 profile_name/base_url 回填到冗余列（一次性迁移）"""
    async with engine.begin() as conn:
        if _is_sqlite:
            await conn.execute(text("""
                UPDATE results
                SET profile_name = COALESCE(json_extract(config_json, '$.profile_name'), ''),
                    base_url = COALESCE(json_extract(config_json, '$.base_url'), '')
                WHERE profile_name = '' OR base_url = ''
            """))
        else:
            await conn.execute(text("""
                UPDATE results
                SET profile_name = COALESCE(config_json::jsonb->>'profile_name', ''),
                    base_url = COALESCE(config_json::jsonb->>'base_url', '')
                WHERE profile_name = '' OR base_url = ''
            """))
```

- [ ] **Step 4: 在 init_db 中调用回填**

在 `init_db()` 函数末尾，`_migrate_schedule_results_profile_name()` 调用之后追加：

```python
    await _backfill_redundant_columns()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_backfill_redundant_columns -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: 冗余列历史数据回填迁移"
```

---

### Task 4: save_result 写入冗余列

**Files:**
- Modify: `app/db.py:491-508` (save_result)
- Modify: `app/db.py:552-674` (get_results_aggregated)
- Modify: `app/db.py:817-889` (get_site_trend)
- Modify: `tests/test_sqlite_optimization.py`

- [ ] **Step 1: 写失败测试——save_result 应写入冗余列**

在 `tests/test_sqlite_optimization.py` 中追加：

```python
@pytest.mark.asyncio
async def test_save_result_populates_redundant_columns():
    """save_result 应从 config_json 提取 profile_name/base_url 写入冗余列"""
    config = json.dumps({"profile_name": "NewSite", "base_url": "https://new.example.com", "model": "gpt-4o"})
    await save_result(
        user_id=1, test_id="rc-test", filename="rc_test.json",
        timestamp="20260425_140000",
        config_json=config, summary_json="{}", percentiles_json="{}",
    )

    async with engine.connect() as conn:
        cur = await conn.execute(text(
            "SELECT profile_name, base_url FROM results WHERE test_id='rc-test'"
        ))
        row = cur.fetchone()
    assert row[0] == "NewSite", f"profile_name 应为 NewSite，实际为 {row[0]}"
    assert row[1] == "https://new.example.com", f"base_url 应为 https://new.example.com，实际为 {row[1]}"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_save_result_populates_redundant_columns -v`
Expected: FAIL — profile_name 为空字符串

- [ ] **Step 3: 修改 save_result**

将 `app/db.py` 的 `save_result` 函数（line 491-508）改为：

```python
async def save_result(user_id: int, test_id: str, filename: str, timestamp: str,
                       config_json: str, summary_json: str, percentiles_json: str,
                       errors_json: str = "{}", error_details_json: str = "[]",
                       group_id: str = "", scheduled_task_id: int = 0):
    # 从 config_json 提取冗余字段
    try:
        _cfg = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        _cfg = {}
    _profile_name = _cfg.get("profile_name", "")
    _base_url = _cfg.get("base_url", "")

    async with engine.begin() as conn:
        await conn.execute(
            text("""INSERT INTO results (user_id, test_id, filename, timestamp, config_json,
                    summary_json, percentiles_json, errors_json, error_details_json, group_id,
                    scheduled_task_id, profile_name, base_url)
                   VALUES (:uid, :test_id, :filename, :timestamp, :config_json,
                    :summary_json, :percentiles_json, :errors_json, :error_details_json, :group_id,
                    :scheduled_task_id, :profile_name, :base_url)"""),
            {"uid": user_id, "test_id": test_id, "filename": filename, "timestamp": timestamp,
             "config_json": config_json, "summary_json": summary_json,
             "percentiles_json": percentiles_json, "errors_json": errors_json,
             "error_details_json": error_details_json, "group_id": group_id,
             "scheduled_task_id": scheduled_task_id,
             "profile_name": _profile_name, "base_url": _base_url},
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_save_result_populates_redundant_columns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: save_result 写入 profile_name/base_url 冗余列"
```

---

### Task 5: get_results_aggregated 去掉 json_extract

**Files:**
- Modify: `app/db.py:552-572` (site_filter 部分)
- Modify: `tests/test_sqlite_optimization.py`

- [ ] **Step 1: 写失败测试——冗余列过滤**

在 `tests/test_sqlite_optimization.py` 中追加：

```python
async def _seed_optimization_data():
    """为优化测试插入数据"""
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"opt-a-{i}", filename=f"opt_a_{i}.json",
            timestamp=f"20260425_{10+i:02d}0000",
            config_json=json.dumps({"profile_name": "SiteA", "base_url": "https://a.com", "model": "gpt-4o"}),
            summary_json=json.dumps({"success_rate": 99.5, "token_throughput_tps": 100}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.5}}),
        )
    for i in range(3):
        await save_result(
            user_id=1, test_id=f"opt-b-{i}", filename=f"opt_b_{i}.json",
            timestamp=f"20260425_{12+i:02d}0000",
            config_json=json.dumps({"profile_name": "SiteB", "base_url": "https://b.com", "model": "claude-opus-4-6"}),
            summary_json=json.dumps({"success_rate": 95.0, "token_throughput_tps": 80}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.8}}),
        )


@pytest.mark.asyncio
async def test_aggregated_filter_by_profile_name():
    """get_results_aggregated 按 profile_name 过滤应只返回匹配数据"""
    await _seed_optimization_data()
    result = await get_results_aggregated(user_id=1, limit=100, profile_name="SiteA")
    for item in result["items"]:
        assert item["config"].get("profile_name") == "SiteA", f"应只返回 SiteA，实际为 {item['config'].get('profile_name')}"
    assert result["total"] == 5, f"应有 5 条 SiteA 数据，实际为 {result['total']}"


@pytest.mark.asyncio
async def test_aggregated_filter_by_base_url():
    """get_results_aggregated 按 base_url 过滤应只返回匹配数据"""
    await _seed_optimization_data()
    result = await get_results_aggregated(user_id=1, limit=100, base_url="https://b.com")
    for item in result["items"]:
        assert item["config"].get("profile_name") == "SiteB"
    assert result["total"] == 3
```

- [ ] **Step 2: 运行测试确认通过（回归）**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_aggregated_filter_by_profile_name tests/test_sqlite_optimization.py::test_aggregated_filter_by_base_url -v`
Expected: PASS（现有逻辑使用 json_extract，冗余列回填后数据一致，测试应直接通过——确认基线）

- [ ] **Step 3: 重写 site_filter 使用冗余列**

将 `app/db.py` 的 `get_results_aggregated` 函数中 `site_filter` 构建部分（line 562-572）替换为：

```python
    site_filter = ""
    if profile_name:
        site_filter = "AND r.profile_name=:profile_name"
        params["profile_name"] = profile_name
    elif base_url:
        base_clean = base_url.rstrip("/")
        base_with_slash = base_clean + "/"
        site_filter = ("AND (r.base_url=:base_url"
                       " OR r.base_url=:base_url_slash)")
        params["base_url"] = base_clean
        params["base_url_slash"] = base_with_slash
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: get_results_aggregated 用冗余列替代 json_extract 过滤"
```

---

### Task 6: get_site_trend 去掉 json_extract

**Files:**
- Modify: `app/db.py:817-836` (site_filter 部分)
- Modify: `tests/test_sqlite_optimization.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sqlite_optimization.py` 中追加：

```python
from app.db import get_site_trend


@pytest.mark.asyncio
async def test_site_trend_filter_by_profile_name():
    """get_site_trend 按 profile_name 过滤应只返回匹配站点的趋势"""
    await _seed_optimization_data()
    trend = await get_site_trend(user_id=1, base_url="", profile_name="SiteA")
    # SiteA 有 5 条数据，应全部出现在趋势中
    total_runs = sum(p["run_count"] for p in trend)
    assert total_runs == 5, f"SiteA 趋势应有 5 次运行，实际为 {total_runs}"
```

- [ ] **Step 2: 运行测试确认通过（回归）**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_site_trend_filter_by_profile_name -v`
Expected: PASS（现有逻辑使用 json_extract，但数据一致所以测试通过——确认基线）

- [ ] **Step 3: 重写 get_site_trend 的 site_filter**

将 `app/db.py` 的 `get_site_trend` 函数中 site_filter 构建部分（line 827-836）替换为：

```python
    if profile_name:
        site_filter = "AND profile_name=:profile_name"
        params["profile_name"] = profile_name
    else:
        base_clean = base_url.rstrip("/")
        base_with_slash = base_clean + "/"
        site_filter = ("AND (base_url=:base_url"
                       " OR base_url=:base_with_slash)")
        params["base_url"] = base_clean
        params["base_with_slash"] = base_with_slash
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: get_site_trend 用冗余列替代 json_extract 过滤"
```

---

### Task 7: get_sites_summary 改用 SQL 聚合

**Files:**
- Modify: `app/db.py:1178-1270` (get_sites_summary)
- Modify: `tests/test_sqlite_optimization.py`

这是最重的优化。当前 `get_sites_summary` 调用 `get_results()` 加载**所有结果**到 Python，然后在内存中分组、计算健康状态和 sparkline。改为用 SQL 直接聚合。

- [ ] **Step 1: 写失败测试**

在 `tests/test_sqlite_optimization.py` 中追加：

```python
from app.db import get_sites_summary, upsert_profile


@pytest.mark.asyncio
async def test_sites_summary_returns_correct_health():
    """get_sites_summary 应正确计算每个站点的健康状态"""
    await upsert_profile(
        user_id=1, name="HealthySite", base_url="https://healthy.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )
    await upsert_profile(
        user_id=1, name="ErrorSite", base_url="https://error.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )

    # HealthySite: 5 条 100% 成功率
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"hs-{i}", filename=f"hs_{i}.json",
            timestamp=f"20260425_{14+i:02d}0000",
            config_json=json.dumps({"profile_name": "HealthySite", "base_url": "https://healthy.com"}),
            summary_json=json.dumps({"success_count": 10, "total_requests": 10, "success_rate": 100.0}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.5}}),
        )

    # ErrorSite: 5 条 50% 成功率
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"es-{i}", filename=f"es_{i}.json",
            timestamp=f"20260425_{14+i:02d}0000",
            config_json=json.dumps({"profile_name": "ErrorSite", "base_url": "https://error.com"}),
            summary_json=json.dumps({"success_count": 5, "total_requests": 10, "success_rate": 50.0}),
            percentiles_json=json.dumps({"TTFT": {"P50": 1.5}}),
        )

    summary = await get_sites_summary(user_id=1)
    by_name = {s["profile"]["name"]: s for s in summary}

    assert by_name["HealthySite"]["health"] == "healthy"
    assert by_name["ErrorSite"]["health"] == "error"
    assert by_name["HealthySite"]["last_test_at"] is not None


@pytest.mark.asyncio
async def test_sites_summary_sparkline_data():
    """get_sites_summary 应返回 sparkline_data"""
    await upsert_profile(
        user_id=1, name="SparkSite", base_url="https://spark.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )
    for i in range(10):
        await save_result(
            user_id=1, test_id=f"sp-{i}", filename=f"sp_{i}.json",
            timestamp=f"20260425_{10+i:02d}0000",
            config_json=json.dumps({"profile_name": "SparkSite", "base_url": "https://spark.com", "model": "gpt-4o"}),
            summary_json=json.dumps({"success_count": 10, "total_requests": 10, "success_rate": 100.0}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.3 + i * 0.05}}),
        )

    summary = await get_sites_summary(user_id=1)
    by_name = {s["profile"]["name"]: s for s in summary}
    spark = by_name["SparkSite"]["sparkline_data"]
    assert "gpt-4o" in spark, "sparkline 应按 model 分组"
    assert len(spark["gpt-4o"]) == 10, f"应有 10 个点，实际为 {len(spark['gpt-4o'])}"
```

- [ ] **Step 2: 运行测试确认通过（回归）**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py::test_sites_summary_returns_correct_health tests/test_sqlite_optimization.py::test_sites_summary_sparkline_data -v`
Expected: PASS（现有实现能正确计算，测试确认基线）

- [ ] **Step 3: 重写 get_sites_summary**

将 `app/db.py` 的 `get_sites_summary` 函数（line 1178-1270）替换为：

```python
async def get_sites_summary(user_id: int, hours: int | None = None) -> list[dict]:
    """获取用户所有站点的最新测试摘要。使用 SQL 聚合避免全量加载。"""
    profiles = await get_profiles(user_id)
    if not profiles:
        return []

    params: dict = {"uid": user_id}
    time_filter = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        time_filter = "AND r.timestamp >= :cutoff"
        params["cutoff"] = cutoff

    summary = {}
    for p in profiles:
        key = p["name"]
        summary[key] = {
            "profile": p,
            "latest_results": [],
            "health": "unknown",
            "last_test_at": None,
            "sparkline_data": {},
        }

    # 构建 scheduled_task_id → profile name 查找表
    scheduled_tasks = await get_scheduled_tasks(user_id)
    task_to_profile = {}
    for st in scheduled_tasks:
        pids = st.get("profile_ids") or []
        if pids:
            task_to_profile[st["id"]] = pids[0]

    # 收集所有 profile_name 列表用于 SQL IN 子句
    profile_names = [p["name"] for p in profiles]
    if not profile_names:
        return list(summary.values())

    # SQL 1：获取每个 profile 的最近 10 条结果（用于健康计算 + latest_results）
    placeholders = ", ".join([f":pn_{i}" for i in range(len(profile_names))])
    pn_params = {f"pn_{i}": name for i, name in enumerate(profile_names)}
    all_params = {**params, **pn_params}

    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"""
                SELECT r.id, r.profile_name, r.timestamp, r.summary_json,
                       r.percentiles_json, r.config_json, r.scheduled_task_id
                FROM results r
                WHERE r.user_id=:uid
                  AND r.profile_name IN ({placeholders})
                  {time_filter}
                ORDER BY r.profile_name, r.created_at DESC
            """),
            all_params,
        )
        rows = cur.fetchall()

    # 分桶：每个 profile 最多保留最近 50 条（用于 sparkline），最近 5 条用于健康计算
    profile_rows: dict[str, list] = {}
    for row in rows:
        pn = row[1]  # profile_name
        if pn not in profile_rows:
            profile_rows[pn] = []
        if len(profile_rows[pn]) < 50:
            profile_rows[pn].append(row)

    for pn, prows in profile_rows.items():
        if pn not in summary:
            continue

        # 解析最近 5 条用于健康判断
        latest_results = []
        for r in prows[:5]:
            try:
                s = json.loads(r[3])  # summary_json
            except (json.JSONDecodeError, TypeError):
                s = {}
            latest_results.append({
                "timestamp": r[2],
                "summary": s,
                "config": json.loads(r[5]) if r[5] else {},
                "scheduled_task_id": r[6],
            })

        summary[pn]["latest_results"] = latest_results
        summary[pn]["last_test_at"] = prows[0][2] if prows else None

        # 健康计算：最近 5 条的成功率均值
        success_rates = []
        for lr in latest_results:
            s = lr["summary"]
            total = s.get("total_requests", 0)
            if total > 0:
                success = s.get("success_count", s.get("successful_requests", 0))
                success_rates.append(success / total)

        if not success_rates:
            summary[pn]["health"] = "unknown"
        else:
            avg_rate = sum(success_rates) / len(success_rates)
            summary[pn]["health"] = "healthy" if avg_rate >= 0.95 else "error"

        # sparkline：按 model 分组提取 TTFT P50
        model_ttfts: dict[str, list[tuple[str, float]]] = {}
        for r in prows:
            try:
                cfg = json.loads(r[5])  # config_json
                model = cfg.get("model", "-")
            except (json.JSONDecodeError, TypeError):
                model = "-"
            try:
                p_json = json.loads(r[4])  # percentiles_json
                ttft = p_json.get("TTFT", {}).get("P50")
            except (json.JSONDecodeError, TypeError):
                ttft = None
            if ttft is not None:
                ts = r[2]  # timestamp
                model_ttfts.setdefault(model, []).append((ts, float(ttft)))

        sparkline_data: dict[str, list[float]] = {}
        for model, pairs in model_ttfts.items():
            pairs.sort(key=lambda x: x[0])
            values = [v for _, v in pairs]
            if len(values) > 50:
                step = len(values) / 50
                values = [values[int(i * step)] for i in range(50)]
            sparkline_data[model] = values
        summary[pn]["sparkline_data"] = sparkline_data

    return list(summary.values())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_sqlite_optimization.py -v`
Expected: PASS

- [ ] **Step 5: 运行完整测试套件确认无回归**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v --timeout=30`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_sqlite_optimization.py
git commit -m "perf: get_sites_summary 改用 SQL 查询，消除全量加载"
```

---

### Task 8: 清理遗留 json_extract + 运行全量回归

**Files:**
- Modify: `app/db.py` (确认无遗留 json_extract)
- Verify: `tests/` 全量测试

- [ ] **Step 1: 搜索遗留 json_extract**

Run: `grep -n "json_extract" app/db.py`
Expected: 只在 `_migrate_schedule_results_profile_name` 和 `_backfill_redundant_columns` 中出现（迁移代码），运行时查询函数不再使用。

如果 `get_results_aggregated` 或 `get_site_trend` 中仍有 `json_extract`，修复。

- [ ] **Step 2: 运行全量测试**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v --timeout=30`
Expected: 全部 PASS

- [ ] **Step 3: Commit（如有修复）**

```bash
git add app/db.py
git commit -m "perf: 清理运行时查询中遗留的 json_extract"
```

---

## 验收检查清单

- [ ] `results` 表有 `idx_results_user_time`、`idx_results_user_sched_time`、`idx_results_user_profile_time`、`idx_results_user_url_time`、`idx_results_filename` 索引
- [ ] `results` 表有 `profile_name` 和 `base_url` 冗余列
- [ ] `save_result` 自动写入冗余列
- [ ] `get_results_aggregated` 不再使用 `json_extract`（迁移代码除外）
- [ ] `get_site_trend` 不再使用 `json_extract`（迁移代码除外）
- [ ] `get_sites_summary` 不再调用 `get_results()` 全量加载
- [ ] 所有现有测试通过
- [ ] 新增测试覆盖索引、冗余列、过滤、健康计算、sparkline
