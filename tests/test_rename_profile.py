"""测试 rename_profile 级联更新"""

import json

import pytest

from app.db import (
    create_user,
    upsert_profile,
    get_profiles,
    create_scheduled_task,
    get_scheduled_task,
    update_scheduled_task,
    delete_profile,
    save_result,
    engine,
    rename_profile,
)
from sqlalchemy import text


@pytest.mark.asyncio
async def test_rename_profile_cascades():
    """改名后 profiles / results / scheduled_tasks 全部同步"""
    uid = await create_user("rename_test@example.com", "pw")

    # 建 profile
    await upsert_profile(uid, "OldSite", base_url="https://api.example.com",
                         models=["gpt-4o"], set_active=True)

    # 建一条结果，profile_name=OldSite
    await save_result(
        user_id=uid,
        test_id="test-123",
        filename="test-123.json",
        timestamp="20260606_120000",
        config_json=json.dumps({"profile_name": "OldSite", "base_url": "https://api.example.com"}),
        summary_json=json.dumps({"success_count": 10, "total_requests": 10}),
        percentiles_json="{}",
        run_id="run-abc",
    )

    # 建一个定时任务，profile_ids 包含 OldSite
    sid = await create_scheduled_task(uid, "daily-check", ["OldSite", "AnotherSite"],
                                      {}, "interval", "300")

    # 执行改名
    result = await rename_profile(uid, "OldSite", "NewSite")
    assert result is True, "rename_profile 应返回 True"

    # 1. profiles.name 已更新
    profiles = await get_profiles(uid)
    names = [p["name"] for p in profiles]
    assert "NewSite" in names, "profiles 中应有 NewSite"
    assert "OldSite" not in names, "profiles 中不应有 OldSite"

    # 2. results.profile_name 已更新
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT profile_name, config_json FROM results WHERE user_id=:uid"),
            {"uid": uid},
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "NewSite", f"results.profile_name 应为 NewSite，实为 {row[0]}"

    # 3. results.config_json 内的 profile_name 已更新
    cfg = json.loads(row[1])
    assert cfg.get("profile_name") == "NewSite", \
        f"config_json.profile_name 应为 NewSite，实为 {cfg.get('profile_name')}"

    # 4. scheduled_tasks.profile_ids 中的 OldSite 已替换为 NewSite
    task = await get_scheduled_task(sid)
    pids = task.get("profile_ids") or []
    assert "NewSite" in pids, f"profile_ids 应含 NewSite，实为 {pids}"
    assert "OldSite" not in pids, f"profile_ids 不应含 OldSite，实为 {pids}"
    assert "AnotherSite" in pids, "profile_ids 中其它元素应保留"


@pytest.mark.asyncio
async def test_rename_profile_conflict():
    """改名为已存在的名字应失败"""
    uid = await create_user("rename_conflict@example.com", "pw")

    await upsert_profile(uid, "SiteA", base_url="https://a.example.com", models=["m1"])
    await upsert_profile(uid, "SiteB", base_url="https://b.example.com", models=["m1"])

    with pytest.raises(ValueError, match=".*已存在.*|.*already exists.*"):
        await rename_profile(uid, "SiteA", "SiteB")


@pytest.mark.asyncio
async def test_rename_profile_same_name():
    """old == new 时直接成功，无操作"""
    uid = await create_user("rename_same@example.com", "pw")
    await upsert_profile(uid, "MySite", base_url="https://api.example.com", models=["m1"])

    result = await rename_profile(uid, "MySite", "MySite")
    assert result is True

    profiles = await get_profiles(uid)
    names = [p["name"] for p in profiles]
    assert "MySite" in names


@pytest.mark.asyncio
async def test_rename_profile_not_found():
    """改名不存在的 profile 应报错"""
    uid = await create_user("rename_notfound@example.com", "pw")

    with pytest.raises((ValueError, LookupError)):
        await rename_profile(uid, "Ghost", "NewGhost")


@pytest.mark.asyncio
async def test_rename_profile_migrates_alert_state():
    """改名后 scheduled_tasks.alert_state 顶层站点 key 跟随迁移，旧名不残留。"""
    uid = await create_user("rename_alert@example.com", "pw")
    await upsert_profile(uid, "OldSite", base_url="https://api.example.com", models=["gpt-4o"])
    sid = await create_scheduled_task(uid, "t", ["OldSite"], {}, "interval", "300")
    await update_scheduled_task(
        sid, alert_state='{"OldSite": {"gpt-4o": {"s": "alerting", "n": 3}}}')

    await rename_profile(uid, "OldSite", "NewSite")

    task = await get_scheduled_task(sid)
    states = json.loads(task["alert_state"])
    assert "OldSite" not in states, "旧名不应残留在 alert_state"
    assert states.get("NewSite", {}).get("gpt-4o", {}).get("s") == "alerting", \
        "告警状态应迁移到新名下"


@pytest.mark.asyncio
async def test_delete_profile_clears_alert_state():
    """删除站点后 scheduled_tasks.alert_state 里该站点 key 被清除。"""
    uid = await create_user("delete_alert@example.com", "pw")
    await upsert_profile(uid, "DelSite", base_url="https://api.example.com", models=["gpt-4o"])
    sid = await create_scheduled_task(uid, "t", ["DelSite"], {}, "interval", "300")
    await update_scheduled_task(
        sid,
        alert_state='{"DelSite": {"gpt-4o": {"s": "alerting", "n": 3}},'
                    ' "KeepSite": {"gpt-4o": {"s": "alerting", "n": 1}}}')

    await delete_profile(uid, "DelSite")

    task = await get_scheduled_task(sid)
    states = json.loads(task["alert_state"])
    assert "DelSite" not in states, "已删除站点不应残留在 alert_state"
    assert "KeepSite" in states, "其它站点的告警状态应保留"


@pytest.mark.asyncio
async def test_rename_profile_active_profile():
    """改名时 is_active 标记跟随新名字"""
    uid = await create_user("rename_active@example.com", "pw")
    await upsert_profile(uid, "ActiveSite", base_url="https://api.example.com",
                         models=["m1"], set_active=True)

    await rename_profile(uid, "ActiveSite", "RenamedSite")

    from app.db import get_active_profile
    active = await get_active_profile(uid)
    assert active is not None
    assert active["name"] == "RenamedSite", \
        f"active profile 应跟随改名为 RenamedSite，实为 {active['name'] if active else None}"
