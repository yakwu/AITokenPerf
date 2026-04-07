<template>
  <section class="auth-page">
    <div class="auth-card">
      <div class="auth-logo">AIToken<span>Perf</span></div>
      <div class="auth-tabs">
        <button class="auth-tab" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button class="auth-tab" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>
      <div class="auth-error" v-show="error">{{ error }}</div>
      <div class="auth-form">
        <div class="form-group" v-show="mode === 'register'">
          <label class="form-label">昵称</label>
          <input class="form-input" v-model="displayName" placeholder="可选">
        </div>
        <div class="form-group">
          <label class="form-label">邮箱</label>
          <input class="form-input" type="email" v-model="email" placeholder="your@email.com" @keydown.enter="submit()">
        </div>
        <div class="form-group">
          <label class="form-label">密码</label>
          <input class="form-input" type="password" v-model="password" placeholder="至少 6 位" @keydown.enter="submit()">
        </div>
        <button class="btn btn-primary" style="width:100%;margin-top:8px" @click="submit()" :disabled="loading">
          <span v-if="!loading">{{ mode === 'login' ? '登录' : '注册' }}</span>
          <span v-else>处理中...</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue';
import { useAppStore } from '../stores/app';
import { loginApi, registerApi } from '../api';
import { toast } from '../composables/useToast';

const store = useAppStore();
const mode = ref('login');
const email = ref('');
const password = ref('');
const displayName = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
  if (!email.value || !password.value) {
    error.value = '请输入邮箱和密码';
    return;
  }
  error.value = '';
  loading.value = true;
  try {
    let res;
    if (mode.value === 'login') {
      res = await loginApi(email.value, password.value);
    } else {
      res = await registerApi(email.value, password.value, displayName.value);
    }
    if (res.error) {
      error.value = res.error;
      return;
    }
    store.setUser(res.user, res.token);
    store.switchTab('dashboard');
  } catch (e) {
    error.value = e.message;
  }
  loading.value = false;
}
</script>
