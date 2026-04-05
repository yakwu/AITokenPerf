# AITokenPerf

AI API 流式接口性能压测工具，专注于测量 TTFT（首 Token 延迟）、TPOT（Token 生成速度）、E2E（端到端延迟）等关键指标。

支持 Claude API 及所有兼容 `/v1/messages` 接口的服务。

## 功能

- **Burst 模式** — 瞬时发起 N 个并发请求，测试峰值性能
- **Sustained 模式** — 持续维持 N 个并发连接，测试稳定性
- **实时监控** — Web UI 实时展示测试进度和指标
- **统计分析** — P50/P95/P99/P99.5 百分位、吞吐量、成功率
- **历史对比** — 多次测试结果对比分析
- **多用户** — 注册/登录，数据隔离，管理员后台

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动

```bash
python3 main.py
```

访问 <http://localhost:8080>，首次使用会进入注册页面。注册后创建 Profile、填写 API Key 和目标地址即可开始测试。

### 管理员

首个注册用户自动成为管理员，可在"用户管理"页面管理其他用户。

## 项目结构

```
├── server.py          # Web 服务 + API 路由
├── main.py            # 入口
├── db.py              # SQLite 数据库层
├── auth.py            # 认证（bcrypt + JWT）
├── client.py          # API 客户端（流式请求）
├── stats.py           # 统计计算
├── logger.py          # 结构化日志
├── migrate.py         # 旧数据迁移
├── static/            # 前端资源
│   ├── index.html
│   ├── css/style.css
│   └── js/
├── data/              # 运行时数据（自动生成，gitignore）
│   ├── data.db        # SQLite 数据库
│   ├── results/       # 压测结果 JSON
│   └── logs/          # 应用日志
└── config.example.yaml
```

## 输出指标

- **TTFT** (Time To First Token) — 从发送请求到收到第一个 token 的延迟
- **TPOT** (Time Per Output Token) — 每个输出 token 的平均生成间隔
- **E2E** (End-to-End) — 请求的端到端总耗时
- **Throughput** — 每秒完成的请求数 / 每秒生成的 token 数
- **Success Rate** — 请求成功率

## License

Apache 2.0
