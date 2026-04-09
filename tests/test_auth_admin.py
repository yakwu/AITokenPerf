"""TDD 测试：预置管理员、强制改密、注册角色"""

import os
import tempfile

import pytest

# 必须在 import app 之前设置环境变量
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir}/test.db"
os.environ["LOG_MODE"] = "stdout"
os.environ["JWT_SECRET"] = "test-secret-key"

import asyncio  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

from app.server import app  # noqa: E402
from app.db import init_db, engine, get_user_by_email  # noqa: E402
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
        # 清空所有表
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


@pytest.mark.asyncio
async def test_preset_admin_exists():
    """预置管理员账号存在且 must_change_password=True"""
    user = await get_user_by_email(DEFAULT_EMAIL)
    assert user is not None
    assert user["role"] == "admin"
    assert user["must_change_password"] in (1, True)


@pytest.mark.asyncio
async def test_login_returns_must_change_password(client: AsyncClient):
    """登录成功后返回 must_change_password 字段"""
    res = await client.post("/api/auth/login", json={
        "email": DEFAULT_EMAIL,
        "password": DEFAULT_PASSWORD,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["must_change_password"] in (1, True)
    assert "token" in data


@pytest.mark.asyncio
async def test_force_change_password(client: AsyncClient):
    """强制改密后 must_change_password 变为 False"""
    # 登录
    res = await client.post("/api/auth/login", json={
        "email": DEFAULT_EMAIL,
        "password": DEFAULT_PASSWORD,
    })
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 改密
    new_password = "NewPass#456"
    res = await client.put("/api/auth/password", json={
        "old_password": DEFAULT_PASSWORD,
        "new_password": new_password,
    }, headers=headers)
    assert res.status_code == 200

    # 验证 must_change_password 已清除
    user = await get_user_by_email(DEFAULT_EMAIL)
    assert user["must_change_password"] in (0, False)

    # 新密码可以登录
    res = await client.post("/api/auth/login", json={
        "email": DEFAULT_EMAIL,
        "password": new_password,
    })
    assert res.status_code == 200
    assert res.json()["user"]["must_change_password"] in (0, False)


@pytest.mark.asyncio
async def test_register_always_user_role(client: AsyncClient):
    """注册新用户始终为 user 角色（即使已有预置管理员）"""
    res = await client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "test123456",
        "display_name": "Test",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "user"
