<template>
  <section class="tab-content active">
    <div class="settings-page">
      <div class="card" style="margin-bottom:20px">
        <div class="card-header">
          <div class="card-title">个人资料</div>
        </div>
        <div class="form-grid" style="max-width:500px">
          <div class="form-group full">
            <label class="form-label">邮箱</label>
            <input class="form-input" :value="store.user?.email || ''" disabled style="opacity:0.6">
          </div>
          <div class="form-group full">
            <label class="form-label">昵称</label>
            <input class="form-input" v-model="displayName" placeholder="输入昵称">
          </div>
        </div>
        <div class="btn-group" style="margin-top:16px">
          <button class="btn btn-primary" @click="saveProfile()" :disabled="profileLoading">
            <span v-if="!profileLoading">保存资料</span>
            <span v-else>保存中...</span>
          </button>
        </div>
        <div class="settings-msg" v-show="profileMsg" :class="profileMsgType">{{ profileMsg }}</div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">修改密码</div>
        </div>
        <div class="form-grid" style="max-width:500px">
          <div class="form-group full">
            <label class="form-label">当前密码</label>
            <input class="form-input" type="password" v-model="oldPassword" placeholder="输入当前密码">
          </div>
          <div class="form-group full">
            <label class="form-label">新密码</label>
            <input class="form-input" type="password" v-model="newPassword" placeholder="至少 6 位">
          </div>
          <div class="form-group full">
            <label class="form-label">确认新密码</label>
            <input class="form-input" type="password" v-model="confirmPassword" placeholder="再次输入新密码" @keydown.enter="changePassword()">
          </div>
        </div>
        <div class="btn-group" style="margin-top:16px">
          <button class="btn btn-primary" @click="changePassword()" :disabled="passwordLoading">
            <span v-if="!passwordLoading">修改密码</span>
            <span v-else>修改中...</span>
          </button>
        </div>
        <div class="settings-msg" v-show="passwordMsg" :class="passwordMsgType">{{ passwordMsg }}</div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue';
import { useAppStore } from '../stores/app';
import { updateProfileApi, changePasswordApi } from '../api';
import { toast } from '../composables/useToast';

const store = useAppStore();
const displayName = ref(store.user?.display_name || '');
const profileLoading = ref(false);
const profileMsg = ref('');
const profileMsgType = ref('');
const oldPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const passwordLoading = ref(false);
const passwordMsg = ref('');
const passwordMsgType = ref('');

async function saveProfile() {
  profileLoading.value = true;
  profileMsg.value = '';
  try {
    const res = await updateProfileApi({ display_name: displayName.value });
    if (res.error) { profileMsg.value = res.error; profileMsgType.value = 'error'; return; }
    store.user = { ...store.user, display_name: displayName.value };
    localStorage.setItem('user', JSON.stringify(store.user));
    profileMsg.value = '已保存';
    profileMsgType.value = 'success';
    toast('资料已更新', 'success');
  } catch (e) {
    profileMsg.value = e.message;
    profileMsgType.value = 'error';
  }
  profileLoading.value = false;
}

async function changePassword() {
  if (newPassword.value.length < 6) {
    passwordMsg.value = '新密码至少 6 位';
    passwordMsgType.value = 'error';
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordMsg.value = '两次密码不一致';
    passwordMsgType.value = 'error';
    return;
  }
  passwordLoading.value = true;
  passwordMsg.value = '';
  try {
    const res = await changePasswordApi({ old_password: oldPassword.value, new_password: newPassword.value });
    if (res.error) { passwordMsg.value = res.error; passwordMsgType.value = 'error'; return; }
    passwordMsg.value = '密码已修改';
    passwordMsgType.value = 'success';
    oldPassword.value = '';
    newPassword.value = '';
    confirmPassword.value = '';
    toast('密码已修改', 'success');
  } catch (e) {
    passwordMsg.value = e.message;
    passwordMsgType.value = 'error';
  }
  passwordLoading.value = false;
}
</script>
