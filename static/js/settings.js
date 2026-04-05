document.addEventListener('alpine:init', () => {
  Alpine.data('settingsTab', () => ({
    displayName: '',
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
    profileLoading: false,
    passwordLoading: false,
    profileMsg: '',
    passwordMsg: '',
    profileMsgType: '',
    passwordMsgType: '',

    init() {
      if (!localStorage.getItem('token')) return;
      this.loadProfile();
    },

    async loadProfile() {
      try {
        const data = await api('/api/auth/me');
        this.displayName = data.display_name || '';
        // sync store
        if (Alpine.store('app').user) {
          Alpine.store('app').user.display_name = data.display_name;
          localStorage.setItem('user', JSON.stringify(Alpine.store('app').user));
        }
      } catch {}
    },

    async saveProfile() {
      this.profileMsg = '';
      this.profileLoading = true;
      try {
        const data = await api('/api/auth/profile', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: this.displayName }),
        });
        if (data.error) {
          this.profileMsg = data.error;
          this.profileMsgType = 'error';
        } else {
          this.profileMsg = '资料已更新';
          this.profileMsgType = 'success';
          if (Alpine.store('app').user) {
            Alpine.store('app').user.display_name = data.display_name;
            localStorage.setItem('user', JSON.stringify(Alpine.store('app').user));
          }
        }
      } catch (e) {
        this.profileMsg = '更新失败: ' + e.message;
        this.profileMsgType = 'error';
      } finally {
        this.profileLoading = false;
      }
    },

    async changePassword() {
      this.passwordMsg = '';
      if (!this.oldPassword || !this.newPassword) {
        this.passwordMsg = '请填写所有密码字段';
        this.passwordMsgType = 'error';
        return;
      }
      if (this.newPassword.length < 6) {
        this.passwordMsg = '新密码至少 6 位';
        this.passwordMsgType = 'error';
        return;
      }
      if (this.newPassword !== this.confirmPassword) {
        this.passwordMsg = '两次输入的新密码不一致';
        this.passwordMsgType = 'error';
        return;
      }

      this.passwordLoading = true;
      try {
        const data = await api('/api/auth/password', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ old_password: this.oldPassword, new_password: this.newPassword }),
        });
        if (data.error) {
          this.passwordMsg = data.error;
          this.passwordMsgType = 'error';
        } else {
          this.passwordMsg = '密码已修改';
          this.passwordMsgType = 'success';
          this.oldPassword = '';
          this.newPassword = '';
          this.confirmPassword = '';
        }
      } catch (e) {
        this.passwordMsg = '修改失败: ' + e.message;
        this.passwordMsgType = 'error';
      } finally {
        this.passwordLoading = false;
      }
    },
  }));
});
