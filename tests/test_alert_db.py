import json

import pytest

from app.db import (
    create_scheduled_task,
    get_scheduled_task,
    update_scheduled_task,
    save_result,
    get_run_success_rate,
)


@pytest.mark.asyncio
async def test_update_alert_enabled_roundtrip():
    sid = await create_scheduled_task(1, "t3", [], {}, "interval", "300")
    await update_scheduled_task(sid, alert_enabled=True)
    assert bool((await get_scheduled_task(sid))["alert_enabled"]) is True
    await update_scheduled_task(sid, alert_enabled=False)
    assert bool((await get_scheduled_task(sid))["alert_enabled"]) is False


@pytest.mark.asyncio
async def test_update_alert_state_persists():
    sid = await create_scheduled_task(1, "t2", [], {}, "interval", "300")
    await update_scheduled_task(sid, alert_state="alerting")
    row = await get_scheduled_task(sid)
    assert row["alert_state"] == "alerting"


@pytest.mark.asyncio
async def test_get_run_success_rate_aggregates():
    for i, (succ, tot) in enumerate([(8, 10), (5, 10)]):
        await save_result(
            user_id=1, test_id=f"t{i}", filename=f"f{i}.json", timestamp="20260604_120000",
            config_json="{}", summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-x",
        )
    assert await get_run_success_rate(["run-x"]) == (13, 20)


@pytest.mark.asyncio
async def test_get_run_success_rate_empty():
    assert await get_run_success_rate([]) == (0, 0)
    assert await get_run_success_rate(["nope"]) == (0, 0)


@pytest.mark.asyncio
async def test_create_task_with_notifier_id():
    from app.db import create_user, create_notifier, create_scheduled_task, get_scheduled_task
    uid = await create_user("tnid@example.com", "pw")
    nid = await create_notifier(uid, "g", "https://open.feishu.cn/hook/z")
    sid = await create_scheduled_task(uid, "t", ["s"], {}, "interval", "300",
                                      alert_notifier_id=nid, alert_threshold=80,
                                      alert_enabled=True)
    row = await get_scheduled_task(sid)
    assert row["alert_notifier_id"] == nid
    assert row["alert_threshold"] == 80


@pytest.mark.asyncio
async def test_notifier_defaults():
    from app.db import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        # 只给 user_id/name，type/webhook 走默认值
        await conn.execute(text(
            "INSERT INTO notifiers (user_id, name) VALUES (1, 'n1')"))
        row = (await conn.execute(text(
            "SELECT type, webhook FROM notifiers WHERE user_id = 1 AND name = 'n1'"
        ))).mappings().one()
        assert row["type"] == "feishu"
        assert row["webhook"] == ""


@pytest.mark.asyncio
async def test_task_alert_notifier_id_default_zero():
    sid = await create_scheduled_task(1, "t", [], {}, "interval", "300")
    row = await get_scheduled_task(sid)
    assert row["alert_notifier_id"] == 0


@pytest.mark.asyncio
async def test_notifier_crud_and_delete_guard():
    from app.db import (create_user, create_notifier, list_notifiers,
                        get_notifier, update_notifier, delete_notifier,
                        create_scheduled_task, update_scheduled_task)
    uid = await create_user("ntf@example.com", "pw")
    nid = await create_notifier(uid, "运维群", "https://open.feishu.cn/hook/a")
    # list
    items = await list_notifiers(uid)
    assert len(items) == 1 and items[0]["name"] == "运维群"
    # get
    n = await get_notifier(nid)
    assert n["webhook"] == "https://open.feishu.cn/hook/a" and n["type"] == "feishu"
    # update
    await update_notifier(nid, name="新名", webhook="https://open.feishu.cn/hook/b")
    assert (await get_notifier(nid))["name"] == "新名"
    # update 留空 webhook = 不改
    await update_notifier(nid, webhook="")
    assert (await get_notifier(nid))["webhook"] == "https://open.feishu.cn/hook/b"
    # 未被引用可删
    ok, refs = await delete_notifier(nid)
    assert ok is True and refs == 0
    # 被任务引用则拒绝
    nid2 = await create_notifier(uid, "群2", "https://open.feishu.cn/hook/c")
    sid = await create_scheduled_task(uid, "t", ["s"], {}, "interval", "300")
    await update_scheduled_task(sid, alert_notifier_id=nid2)
    ok2, refs2 = await delete_notifier(nid2)
    assert ok2 is False and refs2 == 1
    assert await get_notifier(nid2) is not None  # 没被删


@pytest.mark.asyncio
async def test_success_rate_by_cell_groups():
    from app.db import get_run_success_rate_by_cell
    rows = [
        ("SiteA", "gpt-4o", 8, 10),
        ("SiteA", "gpt-4o", 9, 10),   # 同格第二并发档，应累加
        ("SiteA", "claude", 5, 10),
        ("SiteB", "gpt-4o", 10, 10),
    ]
    for i, (pf, model, succ, tot) in enumerate(rows):
        await save_result(
            user_id=1, test_id=f"c{i}", filename=f"c{i}.json", timestamp="20260609_120000",
            config_json=json.dumps({"profile_name": pf, "model": model}),
            summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-cell",
        )
    cells = await get_run_success_rate_by_cell(["run-cell"])
    assert cells[("SiteA", "gpt-4o")] == (17, 20)
    assert cells[("SiteA", "claude")] == (5, 10)
    assert cells[("SiteB", "gpt-4o")] == (10, 10)


@pytest.mark.asyncio
async def test_success_rate_by_cell_model_missing():
    from app.db import get_run_success_rate_by_cell
    await save_result(
        user_id=1, test_id="nm", filename="nm.json", timestamp="20260609_120000",
        config_json=json.dumps({"profile_name": "SiteA"}),  # 无 model
        summary_json=json.dumps({"success_count": 3, "total_requests": 4}),
        percentiles_json="{}", run_id="run-nm",
    )
    cells = await get_run_success_rate_by_cell(["run-nm"])
    assert cells[("SiteA", "-")] == (3, 4)


@pytest.mark.asyncio
async def test_success_rate_by_cell_empty():
    from app.db import get_run_success_rate_by_cell
    assert await get_run_success_rate_by_cell([]) == {}
    assert await get_run_success_rate_by_cell(["nope"]) == {}
