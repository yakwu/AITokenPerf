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

# 定时任务单次执行超时（秒），超时后自动释放锁防止卡死
SCHEDULER_TASK_TIMEOUT = int(os.environ.get("SCHEDULER_TASK_TIMEOUT", "1800"))

# 内存任务清理：每隔多久扫一次、完成后保留多久（grace，防止误删正在被 SSE 查看的任务）
TASK_CLEANUP_INTERVAL = int(os.environ.get("TASK_CLEANUP_INTERVAL", "1800"))
TASK_RETENTION_SECONDS = int(os.environ.get("TASK_RETENTION_SECONDS", "1800"))

# E2E 测试模式：拦截出站 AI API 请求，返回模拟响应
E2E_TEST_MODE = os.environ.get("E2E_TEST_MODE", "") == "1"

# Run Center 并发准入控制。slot 表示一次正在执行的上游并发请求/长连接。
RUN_MAX_USER_SLOTS = int(os.environ.get("RUN_MAX_USER_SLOTS", "5000"))
RUN_MAX_GLOBAL_SLOTS = int(os.environ.get("RUN_MAX_GLOBAL_SLOTS", "20000"))
RUN_MAX_CHILDREN_PER_RUN = int(os.environ.get("RUN_MAX_CHILDREN_PER_RUN", "10"))

# 多用户模式默认禁止环境变量覆盖用户 Profile。单租户部署需要时可显式开启。
ALLOW_PROFILE_ENV_OVERRIDES = os.environ.get("ALLOW_PROFILE_ENV_OVERRIDES", "") == "1"
