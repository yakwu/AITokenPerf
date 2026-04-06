document.addEventListener('alpine:init', () => {
  Alpine.data('schedulesTab', () => ({
    schedules: [],
    profiles: [],
    loading: false,
    showCreateForm: false,
    createForm: {
      name: '',
      profile_ids: [],
      concurrency: 100,
      mode: 'burst',
      max_tokens: 512,
      timeout: 120,
      duration: 120,
      system_prompt: 'You are a helpful assistant.',
      user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
      schedule_value: 300,
    },
    createLoading: false,
    deleteCandidate: null,
    expandedScheduleId: null,
    scheduleHistory: [],
    trendSummary: [],
    historyLoading: false,
    showEditForm: false,
    editLoading: false,
    editForm: {
      id: null,
      name: '',
      profile_ids: [],
      concurrency: 100,
      mode: 'burst',
      max_tokens: 512,
      timeout: 120,
      duration: 120,
      system_prompt: 'You are a helpful assistant.',
      user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
      schedule_value: 300,
    },

    init() {
      if (!localStorage.getItem('token')) return;
      this.refresh();
    },

    async refresh() {
      this.loading = true;
      try {
        const [schedData, profData] = await Promise.all([
          api('/api/schedules'),
          api('/api/profiles'),
        ]);
        this.schedules = schedData.schedules || [];
        this.profiles = (profData.profiles || []).map(p => p.name);
      } catch (e) {
        toast('加载失败: ' + e.message, 'error');
      }
      this.loading = false;
    },

    toggleCreateProfile(name) {
      const idx = this.createForm.profile_ids.indexOf(name);
      if (idx >= 0) {
        this.createForm.profile_ids = this.createForm.profile_ids.filter(n => n !== name);
      } else {
        this.createForm.profile_ids = [...this.createForm.profile_ids, name];
      }
    },

    formatInterval(seconds) {
      const s = parseInt(seconds) || 0;
      if (s < 60) return s + ' 秒';
      if (s < 3600) return (s / 60) + ' 分钟';
      return (s / 3600) + ' 小时';
    },

    formatTime(iso) {
      if (!iso) return '-';
      try {
        const d = new Date(iso + 'Z');
        return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
      } catch {
        return iso;
      }
    },

    async createSchedule() {
      const f = this.createForm;
      if (!f.name.trim()) { toast('请输入任务名称', 'info'); return; }
      if (f.profile_ids.length === 0) { toast('请至少选择一个 Profile', 'info'); return; }
      this.createLoading = true;
      try {
        const res = await api('/api/schedules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: f.name.trim(),
            profile_ids: f.profile_ids,
            configs_json: {
              concurrency_levels: [Number(f.concurrency)],
              mode: f.mode,
              max_tokens: Number(f.max_tokens),
              timeout: Number(f.timeout),
              duration: Number(f.duration),
              system_prompt: f.system_prompt,
              user_prompt: f.user_prompt,
            },
            schedule_type: 'interval',
            schedule_value: String(f.schedule_value),
          }),
        });
        if (res.error) { toast(res.error, 'error'); return; }
        toast('定时任务已创建', 'success');
        this.showCreateForm = false;
        this.resetForm();
        await this.refresh();
      } catch (e) { toast('创建失败: ' + e.message, 'error'); }
      this.createLoading = false;
    },

    resetForm() {
      this.createForm = {
        name: '', profile_ids: [], concurrency: 100, mode: 'burst',
        max_tokens: 512, timeout: 120, duration: 120,
        system_prompt: 'You are a helpful assistant.',
        user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
        schedule_value: 300,
      };
    },

    async pauseSchedule(id) {
      try {
        await api(`/api/schedules/${id}/pause`, { method: 'POST' });
        toast('已暂停', 'info');
        await this.refresh();
      } catch (e) { toast('操作失败: ' + e.message, 'error'); }
    },

    async resumeSchedule(id) {
      try {
        await api(`/api/schedules/${id}/resume`, { method: 'POST' });
        toast('已恢复', 'success');
        await this.refresh();
      } catch (e) { toast('操作失败: ' + e.message, 'error'); }
    },

    async runNow(id) {
      try {
        await api(`/api/schedules/${id}/run-now`, { method: 'POST' });
        toast('已触发执行', 'info');
      } catch (e) { toast('触发失败: ' + e.message, 'error'); }
    },

    async toggleHistory(id) {
      if (this.expandedScheduleId === id) {
        this.expandedScheduleId = null;
        this._destroyTrendCharts();
        return;
      }
      this.expandedScheduleId = id;
      await this.loadHistory(id);
    },

    _destroyTrendCharts() {
      if (window._trendLatencyChart) { window._trendLatencyChart.destroy(); window._trendLatencyChart = null; }
      if (window._trendQualityChart) { window._trendQualityChart.destroy(); window._trendQualityChart = null; }
      // legacy cleanup
      if (window._scheduleTrendChart) { window._scheduleTrendChart.destroy(); window._scheduleTrendChart = null; }
    },

    async loadHistory(id) {
      this.historyLoading = true;
      this.trendSummary = [];
      try {
        const data = await api(`/api/schedules/${id}/results`);
        this.scheduleHistory = data.results || [];
      } catch (e) {
        toast('加载执行记录失败: ' + e.message, 'error');
        this.scheduleHistory = [];
      }
      this.historyLoading = false;
      this._destroyTrendCharts();
      this.$nextTick(() => {
        this.renderTrendSummary();
        this.renderLatencyChart();
        this.renderQualityChart();
      });
    },

    renderTrendSummary() {
      const results = this.scheduleHistory;
      if (!results || results.length === 0) { this.trendSummary = []; return; }

      function avgField(fn) {
        const vals = results.map(r => fn(r)).filter(v => v != null);
        return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      }

      const aSucc = avgField(r => r.summary?.success_rate);
      const aThr = avgField(r => r.summary?.throughput_rps);
      const aTtft = avgField(r => r.percentiles?.TTFT?.P50 != null ? r.percentiles.TTFT.P50 * 1000 : null);
      const aE2e = avgField(r => r.percentiles?.E2E?.P50 != null ? r.percentiles.E2E.P50 * 1000 : null);

      // 环比：最近一半 vs 之前一半的平均值
      const sorted = [...results].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
      const mid = Math.floor(sorted.length / 2);
      const recentHalf = sorted.slice(mid);
      const prevHalf = sorted.slice(0, mid);

      function avgHalf(arr, fn) {
        const vals = arr.map(r => fn(r)).filter(v => v != null);
        return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      }

      const pSucc = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.summary?.success_rate) : null;
      const pThr = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.summary?.throughput_rps) : null;
      const pTtft = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.percentiles?.TTFT?.P50 != null ? r.percentiles.TTFT.P50 * 1000 : null) : null;
      const pE2e = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.percentiles?.E2E?.P50 != null ? r.percentiles.E2E.P50 * 1000 : null) : null;

      function deltaStr(curr, prevVal, unit, higherIsBetter) {
        if (curr == null || prevVal == null) return { delta: '-', deltaStyle: '' };
        const diff = curr - prevVal;
        const absDiff = Math.abs(diff);
        const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
        const isGood = higherIsBetter ? diff >= 0 : diff <= 0;
        const color = diff === 0 ? 'color:var(--text-tertiary)' : isGood ? 'color:var(--success)' : 'color:var(--danger)';
        return { delta: `${arrow} ${absDiff.toFixed(1)}${unit}`, deltaStyle: color };
      }

      const succDelta = deltaStr(aSucc, pSucc, '%', true);
      const thrDelta = deltaStr(aThr, pThr, '/s', true);
      const ttftDelta = aTtft != null ? deltaStr(aTtft, pTtft, 'ms', false) : { delta: '-', deltaStyle: '' };
      const e2eDelta = aE2e != null ? deltaStr(aE2e, pE2e, 'ms', false) : { delta: '-', deltaStyle: '' };

      this.trendSummary = [
        { label: '成功率', value: aSucc != null ? aSucc.toFixed(1) + '%' : '-', valueStyle: aSucc >= 95 ? 'color:var(--success)' : aSucc >= 80 ? 'color:var(--warning)' : 'color:var(--danger)', ...succDelta },
        { label: '吞吐量', value: aThr != null ? aThr.toFixed(1) + '/s' : '-', valueStyle: '', ...thrDelta },
        { label: 'TTFT P50', value: aTtft != null ? aTtft.toFixed(0) + 'ms' : '-', valueStyle: aTtft <= 500 ? 'color:var(--success)' : aTtft <= 2000 ? 'color:var(--warning)' : 'color:var(--danger)', ...ttftDelta },
        { label: 'E2E P50', value: aE2e != null ? aE2e.toFixed(0) + 'ms' : '-', valueStyle: aE2e <= 2000 ? 'color:var(--success)' : aE2e <= 10000 ? 'color:var(--warning)' : 'color:var(--danger)', ...e2eDelta },
      ];
    },

    renderLatencyChart() {
      const results = this.scheduleHistory;
      if (!results || results.length < 2) return;
      const canvas = document.getElementById('trendLatencyCanvas');
      if (!canvas) return;

      const sorted = [...results].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
      const labels = sorted.map(r => fmtTimestamp(r.timestamp));
      const ttftP50 = sorted.map(r => (r.percentiles?.TTFT?.P50 || 0) * 1000);
      const e2eP50 = sorted.map(r => (r.percentiles?.E2E?.P50 || 0) * 1000);

      window._trendLatencyChart = new Chart(canvas, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'TTFT P50 (ms)',
              data: ttftP50,
              borderColor: '#3B7DD6',
              backgroundColor: '#3B7DD618',
              borderWidth: 2,
              pointRadius: 3,
              tension: 0.3,
              fill: true,
            },
            {
              label: 'E2E P50 (ms)',
              data: e2eP50,
              borderColor: '#E85D26',
              backgroundColor: '#E85D2618',
              borderWidth: 2,
              pointRadius: 3,
              tension: 0.3,
              fill: true,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              position: 'top',
              labels: { font: { family: "'DM Sans'", size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 12 },
            },
            tooltip: {
              callbacks: {
                label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(0)} ms`,
              },
            },
          },
          scales: {
            y: {
              title: { display: true, text: 'Latency (ms)', font: { size: 11 } },
              grid: { color: '#F0EEE9' },
              ticks: { font: { family: "'JetBrains Mono'", size: 10 } },
              beginAtZero: true,
            },
            x: {
              grid: { display: false },
              ticks: { font: { family: "'JetBrains Mono'", size: 10 }, maxRotation: 45 },
            },
          },
        },
      });
    },

    renderQualityChart() {
      const results = this.scheduleHistory;
      if (!results || results.length < 2) return;
      const canvas = document.getElementById('trendQualityCanvas');
      if (!canvas) return;

      const sorted = [...results].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
      const labels = sorted.map(r => fmtTimestamp(r.timestamp));
      const throughput = sorted.map(r => r.summary?.throughput_rps || 0);
      const successRate = sorted.map(r => r.summary?.success_rate ?? null);

      window._trendQualityChart = new Chart(canvas, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: '吞吐量 (req/s)',
              data: throughput,
              borderColor: '#2D8B55',
              backgroundColor: '#2D8B5518',
              borderWidth: 2,
              pointRadius: 3,
              tension: 0.3,
              fill: true,
              yAxisID: 'y',
            },
            {
              label: '成功率 (%)',
              data: successRate,
              borderColor: '#F59E3B',
              backgroundColor: '#F59E3B18',
              borderWidth: 2,
              pointRadius: 3,
              tension: 0.3,
              fill: true,
              yAxisID: 'y1',
              borderDash: [5, 3],
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              position: 'top',
              labels: { font: { family: "'DM Sans'", size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 12 },
            },
            tooltip: {
              callbacks: {
                label: ctx => {
                  if (ctx.dataset.yAxisID === 'y1') return `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%`;
                  return `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)} /s`;
                },
              },
            },
          },
          scales: {
            y: {
              position: 'left',
              title: { display: true, text: 'Throughput (req/s)', font: { size: 11 } },
              grid: { color: '#F0EEE9' },
              ticks: { font: { family: "'JetBrains Mono'", size: 10 } },
              beginAtZero: true,
            },
            y1: {
              position: 'right',
              title: { display: true, text: 'Success Rate (%)', font: { size: 11 } },
              grid: { drawOnChartArea: false },
              ticks: { font: { family: "'JetBrains Mono'", size: 10 } },
              min: 0,
              max: 105,
            },
            x: {
              grid: { display: false },
              ticks: { font: { family: "'JetBrains Mono'", size: 10 }, maxRotation: 45 },
            },
          },
        },
      });
    },

    viewResultInHistory(r) {
      window._autoExpandTestId = r.test_id;
      Alpine.store('app').switchTab('history');
    },

    toggleEditProfile(name) {
      const idx = this.editForm.profile_ids.indexOf(name);
      if (idx >= 0) {
        this.editForm.profile_ids = this.editForm.profile_ids.filter(n => n !== name);
      } else {
        this.editForm.profile_ids = [...this.editForm.profile_ids, name];
      }
    },

    startEdit(s) {
      const configs = s.configs || {};
      this.editForm = {
        id: s.id,
        name: s.name || '',
        profile_ids: [...(s.profile_ids || [])],
        concurrency: (configs.concurrency_levels || [100])[0],
        mode: configs.mode || 'burst',
        max_tokens: configs.max_tokens || 512,
        timeout: configs.timeout || 120,
        duration: configs.duration || 120,
        system_prompt: configs.system_prompt || 'You are a helpful assistant.',
        user_prompt: configs.user_prompt || 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
        schedule_value: parseInt(s.schedule_value) || 300,
      };
      this.showEditForm = true;
    },

    async saveEdit() {
      const f = this.editForm;
      if (!f.name.trim()) { toast('请输入任务名称', 'info'); return; }
      if (f.profile_ids.length === 0) { toast('请至少选择一个 Profile', 'info'); return; }
      this.editLoading = true;
      try {
        const res = await api(`/api/schedules/${f.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: f.name.trim(),
            profile_ids: f.profile_ids,
            configs_json: {
              concurrency_levels: [Number(f.concurrency)],
              mode: f.mode,
              max_tokens: Number(f.max_tokens),
              timeout: Number(f.timeout),
              duration: Number(f.duration),
              system_prompt: f.system_prompt,
              user_prompt: f.user_prompt,
            },
            schedule_type: 'interval',
            schedule_value: String(f.schedule_value),
          }),
        });
        if (res.error) { toast(res.error, 'error'); return; }
        toast('已更新', 'success');
        this.showEditForm = false;
        await this.refresh();
      } catch (e) { toast('更新失败: ' + e.message, 'error'); }
      this.editLoading = false;
    },

    requestDelete(id) {
      this.deleteCandidate = id;
    },

    async confirmDelete(id) {
      try {
        await api(`/api/schedules/${id}`, { method: 'DELETE' });
        toast('已删除', 'info');
        this.deleteCandidate = null;
        await this.refresh();
      } catch (e) { toast('删除失败: ' + e.message, 'error'); }
    },
  }));
});
