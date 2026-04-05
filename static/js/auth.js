function authPage() {
  return {
    mode: 'login', // 'login' | 'register'
    email: '',
    password: '',
    displayName: '',
    loading: false,
    error: '',

    switchMode(m) {
      this.mode = m;
      this.error = '';
    },

    async submit() {
      this.error = '';
      if (!this.email || !this.password) {
        this.error = '请填写邮箱和密码';
        return;
      }
      if (this.mode === 'register' && this.password.length < 6) {
        this.error = '密码至少 6 位';
        return;
      }

      this.loading = true;
      try {
        const path = this.mode === 'login' ? '/api/auth/login' : '/api/auth/register';
        const body = { email: this.email, password: this.password };
        if (this.mode === 'register') body.display_name = this.displayName;

        const res = await fetch(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json();

        if (!res.ok) {
          this.error = data.error || '请求失败';
          return;
        }

        Alpine.store('app').setUser(data.user, data.token);
        Alpine.store('app').switchTab('dashboard');
      } catch (e) {
        this.error = '网络错误，请重试';
      } finally {
        this.loading = false;
      }
    },
  };
}
