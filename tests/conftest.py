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
    # 清理内存中的 manager tasks，避免测试间互相影响
    from app.server import manager
    manager._tasks.clear()
    manager._group_tasks.clear()


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
