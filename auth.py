#!/usr/bin/env python3
"""认证模块 — bcrypt 密码哈希 + JWT token"""

import hashlib
import os
import time
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from aiohttp import web

_SECRET_FILE = Path(__file__).parent / "data" / "data.secret"


def _load_or_create_secret() -> str:
    # 优先使用环境变量（SaaS 部署场景）
    env_secret = os.environ.get("JWT_SECRET", "")
    if env_secret:
        return env_secret

    # 开源场景：从本地文件读取，不存在则自动生成
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text().strip()

    secret = os.urandom(32).hex()
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_text(secret)
    return secret


JWT_SECRET = _load_or_create_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 24

PUBLIC_PATHS = {
    "/", "/favicon.ico",
    "/api/auth/login", "/api/auth/register",
}
PUBLIC_PREFIXES = ["/css/", "/js/", "/fonts/", "/vendor/"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_jwt_token(user_id: int, email: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + JWT_EXPIRES_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if _is_public_path(request.path):
        return await handler(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return web.json_response({"error": "Unauthorized"}, status=401)

    token = auth_header[7:]
    payload = decode_jwt_token(token)
    if payload is None:
        return web.json_response({"error": "Unauthorized"}, status=401)

    request["user_id"] = int(payload["sub"])
    request["user_email"] = payload["email"]
    request["user_role"] = payload.get("role", "user")

    return await handler(request)
