# AITokenPerf

AI API 流式接口性能压测工具，专注于测量 TTFT（首 Token 延迟）、TPOT（Token 生成速度）、E2E（端到端延迟）等关键指标。

支持 Claude API 及所有兼容 `/v1/messages` 接口的服务。

## 功能

- **Burst 模式** — 瞬时发起 N 个并发请求，测试峰值性能
- **Sustained 模式** — 持续维持 N 个并发连接，测试稳定性
- **实时监控** — Web UI 实时展示测试进度和指标
- **统计分析** — P50/P95/P99/P99.5 百分位、吞吐量、成功率
- **历史对比** — 多次测试结果对比分析
- **Web UI** — 浏览器可视化操作

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动

```bash
python3 main.py --web
```

访问 http://localhost:8080，在页面上直接创建 Profile、填写 API Key 和目标地址即可开始测试。

## 环境变量

| 变量 | 说明 |
|------|------|
| `CORS_ORIGINS` | 允许的跨域来源（逗号分隔，如 `https://example.com,https://app.example.com`） |
| `LOG_DIR` | 日志目录（默认 `/var/log/aitokenperf`） |

## 输出指标

- **TTFT** (Time To First Token) — 从发送请求到收到第一个 token 的延迟
- **TPOT** (Time Per Output Token) — 每个输出 token 的平均生成间隔
- **E2E** (End-to-End) — 请求的端到端总耗时
- **Throughput** — 每秒完成的请求数 / 每秒生成的 token 数
- **Success Rate** — 请求成功率

## SaaS 部署

前端可以部署到 Cloudflare Pages / Vercel 等静态托管，后端独立运行。

### 后端

```bash
# 设置允许的前端域名
export CORS_ORIGINS=https://aitokenperf.com

# 启动后端服务
python3 main.py --web --port 8080
```

建议用 systemd 管理进程，Caddy 做 HTTPS 反向代理。

### 前端

Cloudflare Pages 构建配置：

- **构建命令**：`bash build.sh`
- **环境变量**：`API_BASE_URL` = `https://api.aitokenperf.com`

前端会自动将 API 请求发送到指定的后端地址。本地开发无需设置，自动使用同源相对路径。

### 安全特性

- CORS 跨域支持（通过 `CORS_ORIGINS` 环境变量配置）
- 滑动窗口限流（按路径分级：压测启动 5次/分钟，轮询 120次/分钟，其他 60次/分钟）
- 恶意扫描自动封禁（扫描 `/wp-admin`、`/.env` 等路径的 IP 自动封禁 24 小时）
- 请求体大小限制（1MB）
- 压测参数输入校验（并发上限 2000、时长上限 3600s 等）
- 结构化日志（JSONL 格式，写入 `/var/log/aitokenperf/app.log`）

### Caddy 配置参考

```
api.aitokenperf.com {
    reverse_proxy localhost:8080

    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Strict-Transport-Security "max-age=31536000"
        -Server
    }

    @blocked path /wp-admin* /.env* /actuator* /.git* /phpmyadmin*
    respond @blocked 404

    log {
        output file /var/log/caddy/access.log {
            roll_size 50mb
            roll_keep 5
        }
        format json
    }
}
```

## License

MIT
