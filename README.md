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

访问 <http://localhost:8080>，在页面上直接创建 Profile、填写 API Key 和目标地址即可开始测试。

## 输出指标

- **TTFT** (Time To First Token) — 从发送请求到收到第一个 token 的延迟
- **TPOT** (Time Per Output Token) — 每个输出 token 的平均生成间隔
- **E2E** (End-to-End) — 请求的端到端总耗时
- **Throughput** — 每秒完成的请求数 / 每秒生成的 token 数
- **Success Rate** — 请求成功率

## License

MIT
