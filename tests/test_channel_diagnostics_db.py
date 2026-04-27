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

    results = await list_channel_diagnostics(user_id=1, limit=10)
    assert len(results) == 3
    assert results[0]["profile_name"] == "profile-2"  # 最新在前
