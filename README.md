# AITokenPerf

AI API 流式接口性能压测工具，专注于测量 TTFT（首 Token 延迟）、TPOT（Token 生成速度）、E2E（端到端延迟）等关键指标。

支持 Claude API 及所有兼容 `/v1/messages` 接口的服务。

## 功能

- **Burst 模式** — 瞬时发起 N 个并发请求，测试峰值性能
- **Sustained 模式** — 持续维持 N 个并发连接，测试稳定性
- **多服务器并行** — 选择多个 Profile 同时跑压测，完成后自动对比分析
- **实时监控** — Web UI 实时展示测试进度和指标
- **统计分析** — P50/P95/P99/P99.5 百分位、吞吐量、成功率
- **历史对比** — 多次测试结果对比分析，指标优劣颜色标注
- **定时任务** — 为指定 Profile 设置定时自动压测（间隔执行）
- **Profile 管理** — 保存多组服务器配置，一键切换
- **多用户** — 注册/登录，数据隔离，管理员后台

## 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/yakwu/AITokenPerf.git
cd AITokenPerf

# 1. 复制环境变量模板，修改密码
cp .env.example .env

# 2. 拉取镜像并启动
docker compose pull
docker compose up -d
```

访问 <http://localhost:8080>，首次启动自动创建管理员账号（密码见 `docker compose logs app`）。

> 镜像托管在 GitHub Container Registry，push 到 main 分支后自动构建。

**本地构建**（不拉取远程镜像）：

```bash
docker compose -f docker-compose.build.yml up -d --build
```

### 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 main.py
```

本地开发默认使用 SQLite，不设置环境变量即可运行。

### 开发模式

需要 [bun](https://bun.sh/) 来构建前端。

```bash
# 同时启动后端 (8080) + 前端 Dev Server (5180)
./start.sh

# 单独构建前端（输出到 static/）
./build.sh
```

前端基于 Vue 3 + Pinia + Chart.js + Vite，源码在 `frontend/` 目录。

### 管理员

首个注册用户自动成为管理员，可在"用户管理"页面管理其他用户。

## 命令行参数

```
python3 main.py [--port PORT] [--host HOST] [--workers N]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | 8080 | Web 服务端口 |
| `--host` | 127.0.0.1 | 绑定地址，设为 `0.0.0.0` 可对外访问 |
| `--workers` | 1 | Worker 进程数 |

## 环境变量

| 变量 | 说明 |
|------|------|
| `DB_PASSWORD` | PostgreSQL 密码（Docker 部署必需） |
| `JWT_SECRET` | JWT 签名密钥（不设置则自动生成 `data/data.secret`） |
| `CORS_ORIGINS` | 允许的跨域来源，逗号分隔 |
| `DATABASE_URL` | 数据库连接 URL，默认 SQLite，设为 PG 则使用 PostgreSQL |
| `LOG_MODE` | 日志模式：`file`（默认）或 `stdout` |
| `HOST` | 默认绑定地址（`--host` 参数优先） |
| `API_KEY` | 环境变量覆盖 Profile 中的 API Key |
| `BASE_URL` | 环境变量覆盖 Profile 中的 Base URL |
| `MODEL` | 环境变量覆盖 Profile 中的 Model |

## 输出指标

- **TTFT** (Time To First Token) — 从发送请求到收到第一个 token 的延迟
- **TPOT** (Time Per Output Token) — 每个输出 token 的平均生成间隔
- **E2E** (End-to-End) — 请求的端到端总耗时
- **Throughput** — 每秒完成的请求数 / 每秒生成的 token 数
- **Success Rate** — 请求成功率

## 项目结构

```
├── main.py              # 入口，CLI 参数解析
├── app/                 # 后端代码（FastAPI）
│   ├── __init__.py
│   ├── config.py        # 集中配置管理（环境变量）
│   ├── server.py        # Web 服务 + API 路由 + 中间件
│   ├── client.py        # API 客户端（SSE 流式请求）
│   ├── stats.py         # 统计计算（百分位、聚合）
│   ├── db.py            # 数据库层（SQLite / PostgreSQL 双模）
│   ├── auth.py          # 认证（bcrypt + JWT）
│   ├── scheduler.py     # 定时任务调度器
│   ├── migrate.py       # 数据库初始化 + schema 迁移
│   └── logger.py        # 结构化日志（JSONL / stdout）
├── scripts/
│   └── migrate_sqlite_to_pg.py  # SQLite → PostgreSQL 数据迁移
├── nginx/
│   └── nginx.conf       # nginx 反向代理配置（SSE 支持）
├── Dockerfile           # 多阶段构建（bun 前端 + Python 运行）
├── docker-compose.yml   # PostgreSQL + 应用双容器编排
├── .dockerignore        # Docker 构建排除规则
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量模板
├── start.sh             # 开发启动脚本
├── build.sh             # 前端构建脚本
├── frontend/            # Vue 3 前端源码
│   ├── src/
│   │   ├── views/       # 页面组件
│   │   ├── components/  # 通用组件
│   │   ├── api/         # API 请求封装
│   │   ├── stores/      # Pinia 状态管理
│   │   └── utils/       # 工具函数
│   └── vite.config.js
├── static/              # 构建产物（由 FastAPI 直接托管）
│   ├── vendor/          # Phosphor 图标
│   └── assets/          # Vite 打包后的 JS/CSS
└── data/                # 运行时数据（自动生成，gitignore）
    ├── data.db          # SQLite 数据库
    └── logs/            # 应用日志
```

## License

Apache 2.0
