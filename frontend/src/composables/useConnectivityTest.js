import { ref, onUnmounted } from 'vue';
import { api } from '../api/index.js';
import { useBenchSSE } from './useBenchSSE.js';
import { toast } from './useToast.js';
import { escHtml } from '../utils/formatters.js';

export function useConnectivityTest() {
  const running = ref(false);
  const progress = ref({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' });
  const logs = ref([]);
  const result = ref(null);
  const error = ref(null);

  const benchSSE = useBenchSSE();
  let elapsedTimer = null;
  let startTime = 0;

  function logLine(html) {
    const time = new Date().toLocaleTimeString();
    logs.value = [...logs.value, `[${time}] ${html}`];
  }

  function cleanup() {
    benchSSE.disconnect();
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function reset() {
    running.value = false;
    progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };
    logs.value = [];
    result.value = null;
    error.value = null;
  }

  async function start(config) {
    reset();
    running.value = true;

    const model = config.model;
    logLine(`<span class="info">连通性验证: ${escHtml(model)}</span>`);

    try {
      const res = await api('/api/bench/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: config.base_url,
          api_key: config.api_key,
          model,
          provider: config.provider || '',
          custom_endpoint: config.custom_endpoint || false,
          concurrency_levels: [1],
          requests_per_level: 1,
          mode: 'burst',
          max_tokens: 512,
          timeout: 120,
          duration: 120,
          system_prompt: 'You are a helpful assistant.',
          user_prompt: 'Say hello.',
        }),
      });

      if (res.error) {
        error.value = res.error;
        toast(res.error, 'error');
        logLine(`<span class="fail">${escHtml(res.error)}</span>`);
        running.value = false;
        return;
      }

      await waitForSSE(model);
    } catch (e) {
      error.value = e.message;
      toast('连通性验证失败: ' + e.message, 'error');
      logLine(`<span class="fail">${escHtml(e.message)}</span>`);
    }
    running.value = false;
  }

  function waitForSSE(modelName) {
    return new Promise((resolve) => {
      startTime = Date.now();
      progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };

      benchSSE.connect((type, d) => {
        switch (type) {
          case 'bench:start':
            logLine(`<span class="info">请求发送中...</span>`);
            break;
          case 'bench:progress':
            progress.value = {
              ...progress.value,
              done: d.done,
              success: d.success,
              failed: d.failed,
              total: d.total,
              elapsed: d.elapsed,
            };
            if (d.elapsed > 0) progress.value.rate = (d.done / d.elapsed).toFixed(1);
            break;
          case 'bench:level_complete':
            result.value = d.result;
            logLine(`<span class="ok">验证完成</span>`);
            break;
          case 'bench:complete':
            cleanup();
            if (!error.value && result.value) {
              toast('连通性验证通过', 'success');
            }
            resolve();
            break;
          case 'bench:stopped':
            cleanup();
            logLine(`<span class="fail">已停止</span>`);
            resolve();
            break;
          case 'bench:error':
            cleanup();
            error.value = d.error;
            logLine(`<span class="fail">错误: ${escHtml(d.error)}</span>`);
            resolve();
            break;
        }
      });

      elapsedTimer = setInterval(() => {
        if (running.value && startTime) {
          progress.value.elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        }
      }, 1000);
    });
  }

  function stop() {
    cleanup();
    running.value = false;
  }

  onUnmounted(() => cleanup());

  return { running, progress, logs, result, error, start, stop, reset };
}
