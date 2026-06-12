import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_sites_availability_smoke(client):
    """鉴权后返回 200 与 {"cells": [...]} 形状（新用户无数据 → 空列表）。"""
    headers = await auth_headers(client)
    r = await client.get("/api/sites/availability?hours=4&buckets=4", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "cells" in body
    assert isinstance(body["cells"], list)


@pytest.mark.asyncio
async def test_sites_availability_requires_auth(client):
    """未带鉴权头 → 401。"""
    r = await client.get("/api/sites/availability")
    assert r.status_code == 401
