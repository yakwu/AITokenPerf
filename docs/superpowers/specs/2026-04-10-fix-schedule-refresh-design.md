# 修复定时任务执行后页面刷新跳转问题

## 背景

用户反馈：定时任务到期自动执行后，前端页面会刷新并跳转到"历史记录"页面，体验很差。

## 根因分析

完整链路：

1. 定时任务执行完毕 → 后端将 `bench:complete` 事件追加到 `task.events` 队列，任务 status 变为 `idle`
2. 用户回到 `/bench` 页面 → `onMounted` 中 `checkRunningStatus()` 调用 `/api/bench/status`
3. 后端仍然返回 running 状态 → 前端 `startSSE()` 连接 SSE
4. SSE 连接后回放所有存量事件（server.py:1452），包括 `bench:complete`
5. `handleEvent('bench:complete')` → 无条件 `store.switchTab('history')` → 强制跳转
6. 如果此时 token 已过期，API 调用 401 → `window.location.href = '/auth'` → 全页面硬刷新

## 方案：方案 A + 定时任务通知

### 改动 1：checkRunningStatus 排除定时任务

**文件：**
- `app/server.py` 第 929-941 行（`/api/bench/status` 返回）
- `frontend/src/views/TestView.vue` 第 799-802 行（`checkRunningStatus`）

**后端改动：** 在 `/api/bench/status` 返回中增加 `scheduled_task_id` 字段：

```python
return {
    "task_id": task.task_id,
    "status": task.status,
    "scheduled_task_id": task.scheduled_task_id or 0,  # 新增
    # ... 其余字段不变
}
```

**前端改动：** 定时任务不启动 SSE 监听：

```javascript
if (data.status === 'running') {
  taskId.value = data.task_id;
  running.value = true;
  store.status = 'running';
  subMode.value = 'single';
  if (!data.scheduled_task_id) startSSE(); // 定时任务不启动 SSE
}
```

### 改动 2：bench:complete 处理增加守卫

**文件：** `frontend/src/views/TestView.vue` 第 632 行

作为防御性编程，在 `bench:complete` 处理中增加运行状态检查：

```javascript
case 'bench:complete':
  stopSSE();
  setRunningState(false);
  toast('测试完成！', 'success');
  logLine('<span class="ok">测试完成！</span>');
  if (lastCompletedFilename.value) store.pendingFilename = lastCompletedFilename.value;
  // 只有当前确实有结果才跳转，避免定时任务的事件误触发
  if (liveResults.value.length > 0) store.switchTab('history');
  break;
```

### 改动 3：401 硬刷新改软导航

**文件：** `frontend/src/api/index.js` 第 9-13 行

将 `window.location.href = '/auth'` 改为 Vue Router 客户端导航，避免全页面硬刷新：

```javascript
if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    import('../router').then(m => m.default.push('/auth'));
    throw new Error('Unauthorized');
}
```

### 改动 4：定时任务结果 toast 通知

**文件：** `frontend/src/views/TestView.vue`（定时任务列表区域）

在定时任务列表中轮询检查执行结果更新，当检测到新结果时弹出轻量 toast 通知。

**实现方式：**
- 在定时任务 subMode 下，每 30 秒轮询一次 `getScheduleResults` 接口
- 对比上次已知的最新结果 ID，发现新结果时 toast 通知
- 通知内容包含任务名称和结果数量
- 不强制跳转，用户可自行展开查看详情

```javascript
// 新增：定时任务结果轮询
const lastKnownResultIds = ref({}); // schedule_id -> latest result id

async function pollScheduleUpdates() {
  for (const s of schedules.value) {
    try {
      const res = await getScheduleResults(s.id, { limit: 1 });
      const results = res.results || [];
      if (results.length > 0) {
        const latestId = results[0].id;
        if (lastKnownResultIds.value[s.id] && lastKnownResultIds.value[s.id] !== latestId) {
          toast(`定时任务「${s.name}」有新执行结果`, 'info');
        }
        lastKnownResultIds.value[s.id] = latestId;
      }
    } catch (e) { /* 静默 */ }
  }
}
```

**生命周期管理：**
- `onMounted` 时初始化已知结果 ID 并启动 30s 轮询定时器
- `onUnmounted` 时清除定时器
- 仅在定时任务子模式（`subMode === 'schedule'`）下轮询

## 涉及文件

| 文件 | 改动 |
|---|---|
| `app/server.py` | `/api/bench/status` 返回增加 `scheduled_task_id` |
| `frontend/src/api/index.js` | 401 处理改用 router.push |
| `frontend/src/views/TestView.vue` | checkRunningStatus 排除定时任务、bench:complete 增加守卫、定时任务结果轮询通知 |

## 验证要点

1. 手动发起测试 → 完成后正常跳转到历史记录页面
2. 定时任务执行 → 页面不刷新、不跳转
3. 定时任务执行后 30s 内 → toast 通知有新结果
4. Token 过期 → 优雅跳转到登录页（无硬刷新）
5. 用户在其他页面时定时任务执行 → 不受影响
