# AITokenPerf

AI API 流式接口性能压测工具，专注于测量 TTFT（首 Token 延迟）、TPOT（Token 生成速度）、E2E（端到端延迟）等关键指标。

支持 Claude API 及所有兼容 `/v1/messages` 接口的服务。

## 功能

- **Burst 模式** — 瞬时发起 N 个并发请求，测试峰值性能
- **Sustained 模式** — 持续维持 N 个并发连接，测试稳定性
- **实时监控** — Web UI 实时展示测试进度和指标
- **统计分析** — P50/P95/P99/P99.5 百分位、吞吐量、成功率
- **历史对比** — 多次测试结果对比分析
- **CLI + Web** — 命令行和浏览器两种使用方式

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

复制配置模板：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入你的 API Key 和目标地址。

或者使用环境变量（优先级高于 config.yaml）：

```bash
export API_KEY=sk-your-key-here
export BASE_URL=https://api.example.com
export MODEL=claude-sonnet-4-6
```

也可以创建 `.env` 文件（参考 `.env.example`）。

### 启动 Web UI

```bash
python3 main.py --web
```

访问 http://localhost:8080

### 命令行模式

```bash
# 使用默认配置
python3 main.py

# 指定并发级别
python3 main.py --concurrency 10 50 100

# 持续模式，运行 60 秒
python3 main.py --mode sustained --duration 60

# 验证连通性
python3 main.py --dry-run
```

## 配置项

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `api_key` | API 密钥 | - |
| `base_url` | 目标 API 地址 | - |
| `model` | 模型名称 | `claude-sonnet-4-6` |
| `mode` | 测试模式 (`burst` / `sustained`) | `burst` |
| `concurrency_levels` | 并发级别列表 | `[10]` |
| `max_tokens` | 每请求最大输出 tokens | `512` |
| `duration` | Sustained 模式持续秒数 | `30` |
| `timeout` | 请求超时秒数 | `60` |

## 环境变量

| 变量 | 对应配置项 |
|------|-----------|
| `API_KEY` | `api_key` |
| `BASE_URL` | `base_url` |
| `MODEL` | `model` |
| `API_VERSION` | `api_version` |

## 输出指标

- **TTFT** (Time To First Token) — 从发送请求到收到第一个 token 的延迟
- **TPOT** (Time Per Output Token) — 每个输出 token 的平均生成间隔
- **E2E** (End-to-End) — 请求的端到端总耗时
- **Throughput** — 每秒完成的请求数 / 每秒生成的 token 数
- **Success Rate** — 请求成功率

## License

MIT
