<template>
  <section class="auth-page">
    <!-- 强制改密表单 -->
    <div class="auth-card" v-if="forceChangePassword">
      <div class="auth-logo">AIToken<span>Perf</span></div>
      <div style="text-align:center;margin-bottom:16px;color:var(--text-secondary);font-size:13px">
        首次登录，请修改默认密码
      </div>
      <div class="auth-error" v-show="error">{{ error }}</div>
      <div class="auth-form">
        <div class="form-group">
          <label class="form-label">新密码</label>
          <input class="form-input" type="password" v-model="newPassword" placeholder="至少 6 位" @keydown.enter="doForceChange()">
        </div>
        <div class="form-group">
          <label class="form-label">确认密码</label>
          <input class="form-input" type="password" v-model="confirmPassword" placeholder="再次输入新密码" @keydown.enter="doForceChange()">
        </div>
        <button class="btn btn-primary" style="width:100%;margin-top:8px" @click="doForceChange()" :disabled="loading">
          <span v-if="!loading">修改密码</span>
          <span v-else>修改中...</span>
        </button>
      </div>
    </div>

    <!-- 登录/注册表单 -->
    <div class="auth-card" v-else>
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
import { loginApi, registerApi, changePasswordApi } from '../api';
import { toast } from '../composables/useToast';

const store = useAppStore();
const mode = ref('login');
const email = ref('');
const password = ref('');
const displayName = ref('');
const error = ref('');
const loading = ref(false);
const forceChangePassword = ref(false);
const newPassword = ref('');
const confirmPassword = ref('');
let pendingToken = null;
let pendingUser = null;
let oldPassword = '';

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
    if (res.user.must_change_password) {
      pendingToken = res.token;
      pendingUser = res.user;
      oldPassword = password.value;
      store.setUser(res.user, res.token);
      forceChangePassword.value = true;
      error.value = '';
      return;
    }
    store.setUser(res.user, res.token);
    store.switchTab('dashboard');
  } catch (e) {
    error.value = e.message;
  }
  loading.value = false;
}

async function doForceChange() {
  if (!newPassword.value || newPassword.value.length < 6) {
    error.value = '新密码至少 6 位';
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次密码不一致';
    return;
  }
  error.value = '';
  loading.value = true;
  try {
    const res = await changePasswordApi({ old_password: oldPassword, new_password: newPassword.value });
    if (res.error) {
      error.value = res.error;
      return;
    }
    // 更新 user 对象，must_change_password 已清除
    pendingUser.must_change_password = false;
    store.setUser(pendingUser, pendingToken);
    toast('密码已修改', 'success');
    store.switchTab('dashboard');
  } catch (e) {
    error.value = e.message;
  }
  loading.value = false;
}
</script>
