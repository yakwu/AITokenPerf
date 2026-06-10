import json
from datetime import datetime, timedelta

import pytest

from app.db import save_result


def _ts(minutes_ago: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y%m%d_%H%M%S")


@pytest.mark.asyncio
async def test_availability_series_buckets():
    """近 4 小时分 4 桶（每桶 1h）：最旧桶 100%、最新桶 80%、中间两桶无数据=None。"""
    from app.db import get_cell_availability_series
    await save_result(
        user_id=1, test_id="avb1", filename="avb1.json", timestamp=_ts(10),
        config_json=json.dumps({"profile_name": "AvS", "model": "m"}),
        summary_json=json.dumps({"success_count": 8, "total_requests": 10}),
        percentiles_json="{}", run_id="avb",
    )
    await save_result(
        user_id=1, test_id="avb2", filename="avb2.json", timestamp=_ts(190),
        config_json=json.dumps({"profile_name": "AvS", "model": "m"}),
        summary_json=json.dumps({"success_count": 10, "total_requests": 10}),
        percentiles_json="{}", run_id="avb",
    )
    cells = await get_cell_availability_series(1, hours=4, buckets=4)
    series = cells[("AvS", "m")]
    assert len(series) == 4
    assert series[0] == 100.0
    assert series[1] is None
    assert series[2] is None
    assert series[3] == 80.0


@pytest.mark.asyncio
async def test_availability_series_missing_model_groups_to_dash():
    """config 无 model → 归 '-'（与 by_cell 口径一致）。"""
    from app.db import get_cell_availability_series
    await save_result(
        user_id=1, test_id="avnm", filename="avnm.json", timestamp=_ts(5),
        config_json=json.dumps({"profile_name": "AvNM"}),
        summary_json=json.dumps({"success_count": 4, "total_requests": 8}),
        percentiles_json="{}", run_id="avnm",
    )
    cells = await get_cell_availability_series(1, hours=4, buckets=4)
    assert cells[("AvNM", "-")][3] == 50.0


@pytest.mark.asyncio
async def test_availability_series_empty_for_fresh_user():
    """全新用户、窗口内无数据 → 空字典。"""
    from app.db import get_cell_availability_series, create_user
    uid = await create_user("avail-empty@example.com", "pw")
    assert await get_cell_availability_series(uid, hours=4, buckets=4) == {}
