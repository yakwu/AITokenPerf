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
              concurrency_levels: [f.concurrency],
              mode: f.mode,
              max_tokens: f.max_tokens,
              timeout: f.timeout,
              duration: f.duration,
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
