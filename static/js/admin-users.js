document.addEventListener('alpine:init', () => {
  Alpine.data('adminUsersTab', () => ({
    users: [],
    loading: false,
    deleteCandidate: null,

    init() {
      if (!localStorage.getItem('token')) return;
      this.refresh();
    },

    async refresh() {
      this.loading = true;
      try {
        const data = await api('/api/admin/users');
        this.users = Array.isArray(data.users) ? data.users : [];
      } catch (e) {
        this.users = [];
        toast('加载用户列表失败: ' + e.message, 'error');
      } finally {
        this.loading = false;
      }
    },

    requestDelete(user) {
      this.deleteCandidate = this.deleteCandidate === user.id ? null : user.id;
    },

    async confirmDelete(userId) {
      try {
        const data = await api('/api/admin/users/' + userId, { method: 'DELETE' });
        if (data.error) {
          toast(data.error, 'error');
        } else {
          toast('用户已删除', 'info');
          this.deleteCandidate = null;
          await this.refresh();
        }
      } catch (e) {
        toast('删除失败: ' + e.message, 'error');
      }
    },

    formatDate(str) {
      if (!str) return '-';
      // SQLite datetime format: YYYY-MM-DDTHH:MM:SS
      return str.replace('T', ' ').slice(0, 16);
    },
  }));
});
