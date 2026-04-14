import { ref } from 'vue';

const notifications = ref([]);
let idCounter = 0;
const MAX = 20;

export function useNotifications() {
  function add(notification) {
    idCounter++;
    notifications.value.push({ ...notification, id: idCounter, time: Date.now(), read: false });
    while (notifications.value.length > MAX) {
      notifications.value.shift();
    }
  }

  function upsert(profileName, models, maxElapsed, isScheduled, success, failed) {
    const existing = notifications.value.find(n => n.profileName === profileName && n.isScheduled === isScheduled && !n.read);
    const totalRuns = (existing?.runCount || 0) + 1;
    const allModels = existing ? [...new Set([...existing.models, ...models])] : [...new Set(models)];
    const modelsText = allModels.length > 2
      ? `${allModels.slice(0, 2).join(', ')} 等 ${allModels.length} 个模型`
      : allModels.join(', ');
    const prefix = isScheduled ? '定时任务' : '单次测试';

    const total = success + failed;
    let resultText;
    if (total === 0) {
      resultText = `用时 ${maxElapsed}s`;
    } else if (failed === 0) {
      resultText = `全部成功 · 用时 ${maxElapsed}s`;
    } else {
      resultText = `${success}/${total} 成功 · 用时 ${maxElapsed}s`;
    }
    const subtitle = totalRuns > 1
      ? `已完成 ${totalRuns} 次 · ${resultText}`
      : resultText;
    const hasFail = failed > 0;

    if (existing) {
      existing.models = allModels;
      existing.modelsText = modelsText;
      existing.subtitle = subtitle;
      existing.runCount = totalRuns;
      existing.hasFail = hasFail;
      existing.time = Date.now();
    } else {
      idCounter++;
      notifications.value.push({
        id: idCounter,
        title: `${prefix}：${profileName || '测试'} 完成`,
        models: allModels,
        modelsText,
        subtitle,
        profileName,
        isScheduled,
        hasFail,
        runCount: totalRuns,
        read: false,
        time: Date.now(),
      });
      while (notifications.value.length > MAX) {
        notifications.value.shift();
      }
    }
  }

  function dismiss(id) {
    notifications.value = notifications.value.filter(n => n.id !== id);
  }

  function markAllRead() {
    for (const n of notifications.value) {
      n.read = true;
    }
  }

  function clearAll() {
    notifications.value = [];
  }

  const unreadCount = () => notifications.value.filter(n => !n.read).length;

  return { notifications, add, upsert, dismiss, markAllRead, clearAll, unreadCount };
}
