"""测试 channel_diagnostics 表的 CRUD 操作"""

import json
import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_save_and_get_channel_diagnostic(client):
    """保存诊断记录并能读取"""
    from app.db import save_channel_diagnostic, get_channel_diagnostic

    diag_id = await save_channel_diagnostic(
        user_id=1,
        profile_name="test-profile",
        model="claude-opus-4-6",
        status="passed",
        overall_risk="low",
        confidence=0.85,
        report_json={
            "schema_version": 1,
            "dimensions": {
                "cache": {
                    "status": "passed",
                    "prompt_cache": {"status": "supported", "hit_rate": 0.83}
                }
            }
        },
    )
    assert diag_id > 0

    result = await get_channel_diagnostic(diag_id, user_id=1)
    assert result is not None
    assert result["profile_name"] == "test-profile"
    assert result["model"] == "claude-opus-4-6"
    assert result["status"] == "passed"
    assert result["overall_risk"] == "low"
    assert result["confidence"] == 0.85
    assert result["report_json"]["schema_version"] == 1


@pytest.mark.asyncio
async def test_get_channel_diagnostic_wrong_user(client):
    """不同用户不能读取别人的诊断记录"""
    from app.db import save_channel_diagnostic, get_channel_diagnostic

    diag_id = await save_channel_diagnostic(
        user_id=1,
        profile_name="test-profile",
        model="claude-opus-4-6",
        status="passed",
        overall_risk="low",
        confidence=0.85,
        report_json={"schema_version": 1},
    )

    result = await get_channel_diagnostic(diag_id, user_id=999)
    assert result is None


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


@pytest.mark.asyncio
async def test_list_channel_diagnostics_filter_by_status(client):
    """按状态筛选诊断记录"""
    from app.db import save_channel_diagnostic, list_channel_diagnostics

    await save_channel_diagnostic(user_id=1, profile_name="p1", model="m1",
        status="passed", overall_risk="low", confidence=0.8, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="p2", model="m1",
        status="warning", overall_risk="medium", confidence=0.5, report_json={})

    items, total = await list_channel_diagnostics(user_id=1, status="passed")
    assert total == 1
    assert items[0]["status"] == "passed"


@pytest.mark.asyncio
async def test_list_channel_diagnostics_filter_by_profile(client):
    """按站点筛选诊断记录"""
    from app.db import save_channel_diagnostic, list_channel_diagnostics

    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m1",
        status="passed", overall_risk="low", confidence=0.8, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-b", model="m1",
        status="passed", overall_risk="low", confidence=0.8, report_json={})

    items, total = await list_channel_diagnostics(user_id=1, profile_name="site-a")
    assert total == 1
    assert items[0]["profile_name"] == "site-a"


@pytest.mark.asyncio
async def test_list_channel_diagnostics_filter_combined(client):
    """组合筛选"""
    from app.db import save_channel_diagnostic, list_channel_diagnostics

    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m1",
        status="passed", overall_risk="low", confidence=0.8, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m2",
        status="warning", overall_risk="medium", confidence=0.5, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-b", model="m1",
        status="passed", overall_risk="low", confidence=0.9, report_json={})

    items, total = await list_channel_diagnostics(user_id=1, profile_name="site-a", model="m1")
    assert total == 1
    assert items[0]["profile_name"] == "site-a"
    assert items[0]["model"] == "m1"


@pytest.mark.asyncio
async def test_list_diagnostic_filter_options(client):
    """返回去重的筛选选项，支持级联"""
    from app.db import save_channel_diagnostic, list_diagnostic_filter_options, create_user

    # 创建第二个用户用于测试用户隔离
    other_uid = await create_user("other@example.com", "hash", "Other")

    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m1", status="passed", overall_risk="low", confidence=0.8, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-a", model="m2", status="warning", overall_risk="medium", confidence=0.5, report_json={})
    await save_channel_diagnostic(user_id=1, profile_name="site-b", model="m1", status="passed", overall_risk="low", confidence=0.9, report_json={})
    await save_channel_diagnostic(user_id=other_uid, profile_name="other", model="m3", status="passed", overall_risk="low", confidence=0.5, report_json={})

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
    opts = await list_diagnostic_filter_options(user_id=other_uid)
    assert opts["profile_names"] == ["other"]
