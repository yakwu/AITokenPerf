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

# 历史查询单次最多加载的结果行数（按 created_at 倒序取最近 N 行）。
# 聚合模式受此约束防止全表加载进内存；命中上限时响应标记 truncated。
RESULTS_QUERY_MAX_ROWS = int(os.environ.get("RESULTS_QUERY_MAX_ROWS", "5000"))

# 数据保留：自动删除超过 N 天的 results。0 = 关闭（默认，避免误删数据）。
# 常驻部署建议显式设置（如 90）以防 results 表无界膨胀。
RESULTS_RETENTION_DAYS = int(os.environ.get("RESULTS_RETENTION_DAYS", "0"))
# 保留策略扫描间隔（秒），默认每天一次。
RESULTS_RETENTION_INTERVAL = int(os.environ.get("RESULTS_RETENTION_INTERVAL", "86400"))

# 每个用户最多可创建的定时任务数量（任务定义存量上限）。
# 与「同时运行的并发数」无关——后者由 BenchTaskManager.MAX_PER_USER 独立硬限制，
# 故调大此值不会增加同时并发，仅放宽可保存的任务条数。
MAX_SCHEDULES_PER_USER = int(os.environ.get("MAX_SCHEDULES_PER_USER", "50"))

# 飞书告警卡片跳转基址；未配置时不生成跳转按钮（向后兼容）。
# 示例：https://app.aitokenperf.com
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")
