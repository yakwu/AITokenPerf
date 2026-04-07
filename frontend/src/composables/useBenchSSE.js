import { ref } from 'vue';

export function useBenchSSE() {
  const source = ref(null);

  function connect(onEvent) {
    disconnect();
    const token = localStorage.getItem('token') || '';
    const url = `/api/bench/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    source.value = es;

    es.onmessage = (e) => {
      // 默认事件（无 event 字段）— 忽略
    };

    // 监听所有已知事件类型
    const eventTypes = ['bench:start', 'bench:progress', 'bench:level_complete', 'bench:complete', 'bench:stopped', 'bench:error', 'bench:idle'];
    for (const type of eventTypes) {
      es.addEventListener(type, (e) => {
        try {
          const data = JSON.parse(e.data);
          onEvent(type, data);
        } catch (_) {}
      });
    }

    es.onerror = () => {
      // EventSource 会自动重连，无需手动处理
    };
  }

  function disconnect() {
    if (source.value) {
      source.value.close();
      source.value = null;
    }
  }

  return { connect, disconnect };
}
