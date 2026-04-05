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
    selectedConcurrency: 100,
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
    profileDraftName: '',
    profileDeleteCandidate: '',
    profileMode: 'selected', // 'selected' | 'new'
    knownModels: [],
    editingProfileName: false,
    profileDirty: false,
    savedProfileConfig: null,

    init() {
      this.loadConfig().then(() => {
        this.loadProfiles().then(() => {
          this.profileMode = this.currentProfileName ? 'selected' : 'new';
          this.snapshotProfileConfig();
        });
      });
      this.loadKnownModels();
      this.checkRunningStatus();
      this.$watch('form.base_url', () => this.checkProfileDirty());
      this.$watch('form.api_key', () => this.checkProfileDirty());
      this.$watch('form.model', () => this.checkProfileDirty());
    },

    // ---- Profile methods ----
    async loadProfiles() {
      try {
        const data = await api('/api/profiles');
        this.profiles = Array.isArray(data.profiles) ? data.profiles : [];
        const active = data.active_profile || '';
        if (active && this.profiles.some(p => p.name === active)) {
          this.currentProfileName = active;
          this.profileDraftName = active;
        }
      } catch {
        this.profiles = [];
      }
    },

    async loadKnownModels() {
      try {
        const data = await api('/api/results');
        const models = (Array.isArray(data) ? data : [])
          .map(r => r.config?.model)
          .filter(Boolean);
        this.knownModels = [...new Set(models)].sort();
      } catch {
        this.knownModels = [];
      }
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

    checkProfileDirty() {
      if (!this.currentProfileName || !this.savedProfileConfig) {
        this.profileDirty = false;
        return;
      }
      const s = this.savedProfileConfig;
      this.profileDirty = (
        this.form.base_url !== (s.base_url || '') ||
        this.form.api_key !== (s.api_key || '') ||
        this.form.model !== (s.model || '')
      );
    },

    snapshotProfileConfig() {
      this.savedProfileConfig = {
        base_url: this.form.base_url,
        api_key: this.form.api_key,
        model: this.form.model,
      };
      this.profileDirty = false;
    },

    startRenameProfile() {
      this.editingProfileName = true;
      this.$nextTick(() => {
        const el = this.$refs.renameInput;
        if (el) { el.focus(); el.select(); }
      });
    },

    cancelRenameProfile() {
      this.profileDraftName = this.currentProfileName;
      this.editingProfileName = false;
    },

    async finishRenameProfile() {
      if (!this.editingProfileName) return;
      this.editingProfileName = false;
      const newName = this.profileDraftName.trim();
      if (!newName || newName === this.currentProfileName) {
        this.profileDraftName = this.currentProfileName;
        return;
      }
      // 重命名：保存为新名字，删除旧的
      try {
        await api('/api/profiles/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: newName,
            base_url: this.form.base_url,
            api_key: this.form.api_key,
            model: this.form.model,
            api_version: '2023-06-01',
          }),
        });
        const oldName = this.currentProfileName;
        await api('/api/profiles/' + encodeURIComponent(oldName), { method: 'DELETE' });
        this.currentProfileName = newName;
        toast('已重命名为「' + newName + '」', 'success');
        await this.loadProfiles();
      } catch (e) {
        toast('重命名失败: ' + e.message, 'error');
        this.profileDraftName = this.currentProfileName;
      }
    },

    async saveAsNewProfile() {
      const name = prompt('另存为新 Profile，输入名称:');
      if (!name || !name.trim()) return;
      const trimmed = name.trim();
      try {
        await api('/api/profiles/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: trimmed,
            base_url: this.form.base_url,
            api_key: this.form.api_key,
            model: this.form.model,
            api_version: '2023-06-01',
          }),
        });
        this.currentProfileName = trimmed;
        this.profileDraftName = trimmed;
        toast('已另存为「' + trimmed + '」', 'success');
        this.snapshotProfileConfig();
        await this.loadProfiles();
      } catch (e) {
        toast('另存失败: ' + e.message, 'error');
      }
    },

    async saveProfile() {
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

      try {
        await api('/api/profiles/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: trimmed,
            base_url: this.form.base_url,
            api_key: this.form.api_key,
            model: this.form.model,
            api_version: '2023-06-01',
          }),
        });
        this.currentProfileName = trimmed;
        this.profileDeleteCandidate = '';
        toast(this.profileDraftExists ? 'Profile 已更新' : 'Profile 已保存', 'success');
        this.snapshotProfileConfig();
        await this.loadProfiles();
      } catch (e) {
        toast('保存失败: ' + e.message, 'error');
      }
    },

    newProfile() {
      this.form.base_url = '';
      this.form.api_key = '';
      this.form.model = '';
      this.currentProfileName = '';
      this.profileDraftName = '';
      this.profileDeleteCandidate = '';
      this.profileMode = 'new';
      this.editingProfileName = false;
      this.savedProfileConfig = null;
      this.profileDirty = false;
    },

    async switchProfile(name) {
      try {
        const data = await api('/api/profiles/switch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        if (data.error) { toast(data.error, 'error'); return; }
        const c = data.config || {};
        this.form.base_url = c.base_url || '';
        this.form.api_key = c.api_key || '';
        this.form.model = c.model || '';
        this.currentProfileName = name;
        this.profileDraftName = name;
        this.profileDeleteCandidate = '';
        this.profileMode = 'selected';
        this.editingProfileName = false;
        this.snapshotProfileConfig();
      } catch (e) {
        toast('切换失败: ' + e.message, 'error');
      }
    },

    requestDeleteProfile(name) {
      this.profileDeleteCandidate = this.profileDeleteCandidate === name ? '' : name;
    },

    cancelDeleteProfile() {
      this.profileDeleteCandidate = '';
    },

    async confirmDeleteProfile(name) {
      try {
        await api('/api/profiles/' + encodeURIComponent(name), { method: 'DELETE' });
        if (this.currentProfileName === name) {
          this.currentProfileName = '';
        }
        if (this.profileDraftName === name) {
          this.profileDraftName = '';
        }
        this.profileDeleteCandidate = '';
        toast('Profile 已删除', 'info');
        await this.loadProfiles();
      } catch (e) {
        toast('删除失败: ' + e.message, 'error');
      }
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
        this.selectedConcurrency = c.concurrency_levels[0];
      }
    },

    getFormConfig() {
      const conc = this.selectedConcurrency || 100;
      const requests = parseInt(this.requestsPerLevel);
      const config = {
        base_url: this.form.base_url,
        api_key: this.form.api_key,
        model: this.form.model,
        concurrency_levels: [conc],
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
      this.selectedConcurrency = val;
    },

    addCustomConcurrency() {
      const val = parseInt(this.customConcurrency);
      if (!val || val <= 0) return;
      this.selectedConcurrency = val;
      if (!this.concurrencyPresets.includes(val)) {
        this.concurrencyPresets = [...this.concurrencyPresets, val].sort((a, b) => a - b);
      }
      this.customConcurrency = '';
    },
  }));
});
