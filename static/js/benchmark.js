document.addEventListener('alpine:init', () => {
  Alpine.data('benchmarkTab', () => ({
    form: {
      base_url: '',
      api_key: '',
      model: '',
      max_tokens: 512,
      mode: 'burst',
      duration: 120,
      timeout: 120,
      system_prompt: 'You are a helpful assistant.',
      user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
    },
    showApiKey: false,
    concurrencyPresets: [1, 10, 50, 100, 200, 500, 1000],
    selectedConcurrency: new Set([100]),
    customConcurrency: '',
    requestsPerLevel: '',
    running: false,
    progress: { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' },
    logs: [],
    liveResults: [],
    evtSource: null,

    // Profile management
    profiles: [],
    currentProfileName: '',
    profileComposerOpen: false,
    profileDraftName: '',
    profileDeleteCandidate: '',

    init() {
      this.loadProfiles();
      this.loadConfig();
      this.checkRunningStatus();
    },

    // ---- Profile methods ----
    loadProfiles() {
      try {
        const raw = JSON.parse(localStorage.getItem('aitokenperf_profiles') || '[]');
        this.profiles = Array.isArray(raw) ? raw : [];
      } catch {
        this.profiles = [];
      }
    },

    _saveProfiles() {
      localStorage.setItem('aitokenperf_profiles', JSON.stringify(this.profiles));
    },

    toggleProfileComposer() {
      if (this.profileComposerOpen) {
        this.closeProfileComposer();
        return;
      }
      this.profileComposerOpen = true;
      this.profileDraftName = this.currentProfileName || this.profileDraftName || '';
      this.profileDeleteCandidate = '';
      this.$nextTick(() => {
        this.$refs.profileNameInput?.focus();
      });
    },

    closeProfileComposer() {
      this.profileComposerOpen = false;
      this.profileDraftName = this.currentProfileName || '';
    },

    get currentProfile() {
      return this.profiles.find(p => p.name === this.currentProfileName) || null;
    },

    get orderedProfiles() {
      return [...this.profiles].sort((a, b) => {
        if (a.name === this.currentProfileName) return -1;
        if (b.name === this.currentProfileName) return 1;
        return a.name.localeCompare(b.name, 'zh-Hans-CN', { sensitivity: 'base' });
      });
    },

    get profileDraftExists() {
      const trimmed = this.profileDraftName.trim();
      if (!trimmed) return false;
      return this.profiles.some(p => p.name === trimmed);
    },

    profileReadyFieldCount() {
      return [
        this.form.base_url,
        this.form.api_key,
        this.form.model,
      ].filter(v => String(v || '').trim()).length;
    },

    canSaveProfile() {
      return Boolean(
        this.profileDraftName.trim() &&
        this.form.base_url.trim() &&
        this.form.model.trim()
      );
    },

    saveProfile() {
      const trimmed = this.profileDraftName.trim();
      if (!trimmed) {
        toast('请输入 Profile 名称', 'info');
        return;
      }
      if (!this.form.base_url.trim()) {
        toast('请先填写目标地址', 'info');
        return;
      }
      if (!this.form.model.trim()) {
        toast('请先填写模型名称', 'info');
        return;
      }

      const profile = {
        name: trimmed,
        base_url: this.form.base_url,
        api_key: this.form.api_key,
        model: this.form.model,
        api_version: '2023-06-01',
      };

      const idx = this.profiles.findIndex(p => p.name === trimmed);
      if (idx >= 0) {
        this.profiles[idx] = profile;
      } else {
        this.profiles.push(profile);
      }
      this.profiles = [...this.profiles];
      this._saveProfiles();
      this.currentProfileName = trimmed;
      this.profileDeleteCandidate = '';
      this.closeProfileComposer();
      toast(idx >= 0 ? 'Profile 已更新' : 'Profile 已保存', 'success');
    },

    switchProfile(name) {
      const p = this.profiles.find(p => p.name === name);
      if (!p) return;
      this.form.base_url = p.base_url || '';
      this.form.api_key = p.api_key || '';
      this.form.model = p.model || '';
      this.currentProfileName = name;
      this.profileDraftName = name;
      this.profileComposerOpen = false;
      this.profileDeleteCandidate = '';
    },

    requestDeleteProfile(name) {
      this.profileDeleteCandidate = this.profileDeleteCandidate === name ? '' : name;
      this.profileComposerOpen = false;
    },

    cancelDeleteProfile() {
      this.profileDeleteCandidate = '';
    },

    confirmDeleteProfile(name) {
      this.profiles = this.profiles.filter(p => p.name !== name);
      this._saveProfiles();
      if (this.currentProfileName === name) {
        this.currentProfileName = '';
      }
      if (this.profileDraftName === name) {
        this.profileDraftName = '';
      }
      this.profileDeleteCandidate = '';
      toast('Profile 已删除', 'info');
    },

    profileHost(baseUrl) {
      if (!baseUrl) return '未设置目标地址';
      try {
        return new URL(baseUrl).host;
      } catch {
        return baseUrl;
      }
    },

    maskProfileKey(apiKey) {
      if (!apiKey) return '未填写 Key';
      return apiKey.length > 4 ? `Key ••••${apiKey.slice(-4)}` : 'Key 已填写';
    },

    async checkRunningStatus() {
      const status = await api('/api/bench/status');
      if (status.status === 'running') {
        this.running = true;
        Alpine.store('app').status = 'running';
        Alpine.store('app').tab = 'benchmark';
        this.connectSSE();
      }
    },

    async loadConfig() {
      const c = await api('/api/config');
      this.form.base_url = c.base_url || '';
      this.form.api_key = c.api_key || '';
      this.form.model = c.model || '';
      this.form.max_tokens = c.max_tokens || 512;
      this.form.timeout = c.timeout || 120;
      this.form.duration = c.duration || 120;
      this.form.system_prompt = c.system_prompt || '';
      this.form.user_prompt = c.user_prompt || '';
      const mode = c.mode || 'burst';
      this.form.mode = mode;
      if (c.concurrency_levels && c.concurrency_levels.length) {
        this.selectedConcurrency = new Set(c.concurrency_levels);
      }
    },

    getFormConfig() {
      const conc = [...this.selectedConcurrency].sort((a, b) => a - b);
      const requests = parseInt(this.requestsPerLevel);
      const config = {
        base_url: this.form.base_url,
        api_key: this.form.api_key,
        model: this.form.model,
        concurrency_levels: conc.length ? conc : [100],
        mode: this.form.mode,
        max_tokens: parseInt(this.form.max_tokens) || 512,
        timeout: parseInt(this.form.timeout) || 120,
        duration: parseInt(this.form.duration) || 120,
        system_prompt: this.form.system_prompt,
        user_prompt: this.form.user_prompt,
      };
      if (!isNaN(requests) && requests > 0) config.requests_per_level = requests;
      return config;
    },

    async startBench() {
      const config = this.getFormConfig();
      try {
        const res = await api('/api/bench/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        });
        if (res.error) { toast(res.error, 'error'); return; }
        this.setRunningState(true);
        this.connectSSE();
        toast('\u6d4b\u8bd5\u5df2\u542f\u52a8', 'success');
      } catch (e) { toast('\u542f\u52a8\u5931\u8d25: ' + e.message, 'error'); }
    },

    async stopBench() {
      await api('/api/bench/stop', { method: 'POST' });
      toast('\u6b63\u5728\u505c\u6b62...', 'info');
    },

    async dryRun() {
      const config = this.getFormConfig();
      config.concurrency_levels = [1];
      config.requests_per_level = 1;
      config.mode = 'burst';
      try {
        const res = await api('/api/bench/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        });
        if (res.error) { toast(res.error, 'error'); return; }
        this.setRunningState(true);
        this.connectSSE();
        toast('\u8fde\u901a\u6027\u9a8c\u8bc1\u5df2\u542f\u52a8\uff081 \u4e2a\u8bf7\u6c42\uff09', 'info');
      } catch (e) { toast('\u5931\u8d25: ' + e.message, 'error'); }
    },

    setRunningState(running) {
      this.running = running;
      if (running) {
        this.logs = [];
        this.liveResults = [];
        this.progress = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };
      }
      Alpine.store('app').status = running ? 'running' : 'idle';
    },

    connectSSE() {
      if (this.evtSource) this.evtSource.close();
      this.evtSource = new EventSource('/api/bench/stream');

      this.evtSource.addEventListener('bench:start', e => {
        const d = JSON.parse(e.data);
        this.logLine(`<span class="info">[\u7b2c ${d.current_level}/${d.total_levels} \u7ea7] \u542f\u52a8 \u5e76\u53d1=${d.concurrency} \u6a21\u5f0f=${d.mode}</span>`);
      });

      this.evtSource.addEventListener('bench:progress', e => {
        const d = JSON.parse(e.data);
        this.progress.done = d.done;
        this.progress.success = d.success;
        this.progress.failed = d.failed;
        this.progress.elapsed = d.elapsed;
        this.progress.total = d.total;
        if (d.elapsed > 0) {
          this.progress.rate = (d.done / d.elapsed).toFixed(1);
        }
      });

      this.evtSource.addEventListener('bench:level_complete', e => {
        const d = JSON.parse(e.data);
        this.logLine(`<span class="ok">[\u5b8c\u6210] \u5e76\u53d1=${d.concurrency} \u2713</span>`);
        this.liveResults = [...this.liveResults, { concurrency: d.concurrency, result: d.result }];
      });

      this.evtSource.addEventListener('bench:complete', e => {
        this.evtSource.close();
        this.evtSource = null;
        this.setRunningState(false);
        toast('\u6d4b\u8bd5\u5b8c\u6210\uff01', 'success');
        this.logLine('<span class="ok">\u6d4b\u8bd5\u5b8c\u6210\uff01</span>');
      });

      this.evtSource.addEventListener('bench:stopped', e => {
        this.evtSource.close();
        this.evtSource = null;
        this.setRunningState(false);
        toast('\u6d4b\u8bd5\u5df2\u505c\u6b62', 'info');
        this.logLine('<span class="fail">\u6d4b\u8bd5\u5df2\u88ab\u7528\u6237\u505c\u6b62</span>');
      });

      this.evtSource.addEventListener('bench:error', e => {
        const d = JSON.parse(e.data);
        this.evtSource.close();
        this.evtSource = null;
        this.setRunningState(false);
        toast('\u9519\u8bef: ' + d.error, 'error');
        this.logLine(`<span class="fail">\u9519\u8bef: ${d.error}</span>`);
      });

      this.evtSource.onerror = () => {};
    },

    logLine(html) {
      const time = new Date().toLocaleTimeString();
      this.logs = [...this.logs, `[${time}] ${html}`];
      this.$nextTick(() => {
        const el = this.$refs.progressLog;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    toggleConcurrency(val) {
      if (this.selectedConcurrency.has(val)) {
        this.selectedConcurrency.delete(val);
      } else {
        this.selectedConcurrency.add(val);
      }
      // Force Alpine reactivity by reassigning
      this.selectedConcurrency = new Set(this.selectedConcurrency);
    },

    addCustomConcurrency() {
      const val = parseInt(this.customConcurrency);
      if (!val || val <= 0) return;
      this.selectedConcurrency.add(val);
      this.selectedConcurrency = new Set(this.selectedConcurrency);
      if (!this.concurrencyPresets.includes(val)) {
        this.concurrencyPresets = [...this.concurrencyPresets, val].sort((a, b) => a - b);
      }
      this.customConcurrency = '';
    },
  }));
});
