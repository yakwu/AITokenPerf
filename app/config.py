#!/usr/bin/env python3
"""集中配置管理 — 从环境变量读取所有配置"""

import os

# 数据库：本地默认 SQLite，生产用 PostgreSQL
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/data.db")

# 日志模式：file（默认）| stdout
LOG_MODE = os.environ.get("LOG_MODE", "file")

# CORS 允许的跨域来源，逗号分隔；空字符串 = 开发模式
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "")

# JWT 签名密钥；空字符串 = 自动生成 data/data.secret
JWT_SECRET = os.environ.get("JWT_SECRET", "")
