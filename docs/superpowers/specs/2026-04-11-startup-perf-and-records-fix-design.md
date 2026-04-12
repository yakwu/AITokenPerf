# 启动性能优化 + 站点执行记录修复

**日期：** 2026-04-11

## 问题 1：启动阻塞在价格数据下载

### 现象

启动时卡在 `正在从 GitHub 下载模型价格数据...` 30 秒后报 `TimeoutError`，即使本地已有可用缓存。

### 根因

`app/pricing.py:58` — `start()` 在缓存超过 24h 后同步 `await self.refresh()`，阻塞整个 FastAPI lifespan 启动。GitHub raw content 在国内网络环境下经常超时。

### 修复方案

**文件：** `app/pricing.py`

1. `start()` 只加载本地缓存后立即返回，不阻塞
2. 缓存过期时用 `asyncio.create_task(self.refresh())` 后台异步刷新
3. `refresh()` 增加 jsdelivr CDN 镜像作为首选源，GitHub raw 作为备选
4. 超时从 30s 缩短到 10s
5. 首次启动无缓存时也不阻塞（价格数据暂时为空，后台补充）

### CDN 镜像 URL

```
https://cdn.jsdelivr.net/gh/BerriAI/litellm@main/model_prices_and_context_window.json
```

---

## 问题 2：站点历史趋势执行记录为空

### 现象

目标站点 → 历史趋势 → 执行记录表格永远显示「暂无执行记录」。

### 根因

`SiteTrendsTab.vue:182` 用 `r.config?.profile_name === profileName` 前端过滤，但 `config_json` 中**从未存储 `profile_name`**（benchmark 启动时 `profile_name` 只赋给 `BenchTask` 对象，不放入 config）。导致过滤结果永远为空。

此外，即使换成正确字段，前端先拉 20 条全局数据再本地过滤也会导致：
- 分页 total 不准（是全局 total，不是该站点的）
- 有可能前 20 条里没有当前站点的数据

### 修复方案

**文件：** `app/db.py`、`app/server.py`、`frontend/src/components/SiteTrendsTab.vue`

1. **后端** `/api/results` 增加可选查询参数 `base_url`
2. **后端** `get_results_aggregated()` 新增 `base_url` 参数，SQL 增加 `json_extract(config_json, '$.base_url')` 过滤条件（复用 `get_site_trend` 的同款逻辑，包括去尾斜杠兼容）
3. **前端** `loadRecords()` 传入 `profile.base_url` 参数
4. **前端** 移除 `r.config?.profile_name === profileName` 本地过滤
5. `recordsTotal` 直接使用后端返回的 total

---

## 改动文件清单

| 文件 | 改动 |
|------|------|
| `app/pricing.py` | start() 异步化 + refresh() 镜像备选 + 超时缩短 |
| `app/db.py` | `get_results_aggregated()` 新增 `base_url` 过滤 |
| `app/server.py` | `/api/results` 接收 `base_url` 参数 |
| `frontend/src/components/SiteTrendsTab.vue` | loadRecords 传 base_url，去掉前端过滤 |
| `frontend/src/api/index.js` | getResults 支持 base_url 参数（如需要） |

## 风险评估

- 两个修复互相独立，不存在耦合
- 价格服务改为异步刷新是纯后端改动，对前端无影响
- 执行记录改为后端过滤，使用已有的 `json_extract` 模式，风险低
