"""测试 issue #25：历史查询分页下推 SQL + 聚合行数上限 + 数据保留。

回归点：
- get_results_aggregated 此前无 LIMIT，全表加载进内存
- 无任何按时间清理老 results 的机制
"""

import json
import pytest
from sqlalchemy import text

import app.config as cfg
from app.db import (
    engine,
    save_result,
    get_results_aggregated,
    delete_results_older_than,
)


def _cfg_json(profile_name="Site", base_url="https://api.example.com"):
    return json.dumps({"profile_name": profile_name, "base_url": base_url, "model": "gpt-4"})


def _summary():
    return json.dumps({"success_rate": 100.0, "token_throughput_tps": 50.0})


async def _seed_manual(n: int, user_id: int = 1):
    for i in range(n):
        await save_result(
            user_id=user_id, test_id=f"m-{i}", filename=f"m_{i}.json",
            timestamp=f"2026010{i % 9}_120000",
            config_json=_cfg_json(), summary_json=_summary(),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.5}}),
        )


# ---- raw 模式：分页下推到 SQL ----

@pytest.mark.asyncio
async def test_raw_pagination_pushdown_total_and_page():
    await _seed_manual(5)

    page1 = await get_results_aggregated(1, limit=2, offset=0, raw=True)
    assert page1["total"] == 5, "total 应为全部匹配行数"
    assert len(page1["items"]) == 2, "应只返回一页"

    page3 = await get_results_aggregated(1, limit=2, offset=4, raw=True)
    assert page3["total"] == 5
    assert len(page3["items"]) == 1, "最后一页只剩 1 条"


@pytest.mark.asyncio
async def test_raw_empty():
    res = await get_results_aggregated(1, limit=10, offset=0, raw=True)
    assert res["total"] == 0
    assert res["items"] == []


# ---- 聚合模式：行数上限，防止全表加载 ----

@pytest.mark.asyncio
async def test_aggregated_caps_rows_and_flags_truncated(monkeypatch):
    monkeypatch.setattr(cfg, "RESULTS_QUERY_MAX_ROWS", 3)
    await _seed_manual(5)

    res = await get_results_aggregated(1, limit=50, offset=0, raw=False)
    assert res.get("truncated") is True, "超过上限应标记 truncated"
    # 手动结果不聚合，逐条返回；受上限约束应 <= 3
    assert len(res["items"]) <= 3


@pytest.mark.asyncio
async def test_aggregated_not_truncated_when_under_cap(monkeypatch):
    monkeypatch.setattr(cfg, "RESULTS_QUERY_MAX_ROWS", 100)
    await _seed_manual(3)

    res = await get_results_aggregated(1, limit=50, offset=0, raw=False)
    assert res.get("truncated") is False
    assert len(res["items"]) == 3


# ---- 数据保留 ----

async def _age_row(filename: str, created_at: str):
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE results SET created_at=:c WHERE filename=:f"),
            {"c": created_at, "f": filename},
        )


@pytest.mark.asyncio
async def test_retention_deletes_old_keeps_recent():
    await _seed_manual(2)
    # 把 m_0 调成很久以前
    await _age_row("m_0.json", "2000-01-01 00:00:00")

    deleted = await delete_results_older_than(30)
    assert deleted == 1, "应删除 1 条过期数据"

    remaining = await get_results_aggregated(1, limit=50, offset=0, raw=True)
    files = {it["filename"] for it in remaining["items"]}
    assert "m_0.json" not in files, "过期数据应被删除"
    assert "m_1.json" in files, "新数据应保留"


@pytest.mark.asyncio
async def test_retention_disabled_when_zero():
    await _seed_manual(2)
    await _age_row("m_0.json", "2000-01-01 00:00:00")

    deleted = await delete_results_older_than(0)
    assert deleted == 0, "days<=0 表示关闭，不应删除任何数据"

    remaining = await get_results_aggregated(1, limit=50, offset=0, raw=True)
    assert remaining["total"] == 2
