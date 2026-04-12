# 站点卡片交互优化

**日期：** 2026-04-11

## 问题

1. 站点卡片名称不可点击，用户预期点击名称能进入详情
2. "详情"按钮跳转默认 tab 是"单次测试"，用户进详情页更想先看历史数据
3. "一键测试"无确认直接发起请求，容易误操作

## 改动

### 1. 站点名称可点击

- `.site-name` 从 `<span>` 改为 `<router-link to="/sites/:name?tab=trends">`
- hover 样式：accent 色 + 下划线

### 2. "详情"按钮默认跳历史趋势

- `goDetail()` 路由加 `?tab=trends`
- SiteDetailView 已有 `tabQueryMap` 映射 `trends → history`，无需额外改动

### 3. "一键测试"确认弹窗

- SitesView 内新增 inline Modal，显示：站点名、base_url、模型、参数概要
- `testSite()` 改为弹出 Modal，`confirmTest()` 确认后才调用 API
- 「取消」和「确认测试」两个按钮

## 改动文件

| 文件 | 改动 |
|------|------|
| `frontend/src/views/SitesView.vue` | 名称可点击 + 详情跳转改 tab + 一键测试确认弹窗 |
