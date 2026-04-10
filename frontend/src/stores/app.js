import { defineStore } from 'pinia';
import { ref } from 'vue';
import { useRouter } from 'vue-router';

const VALID_TABS = ['dashboard', 'bench', 'history', 'config', 'settings', 'auth', 'admin-users', 'models'];

function isLoggedIn() {
  return !!localStorage.getItem('token');
}

export const useAppStore = defineStore('app', () => {
  const router = useRouter();
  const userStr = localStorage.getItem('user');
  const user = ref(userStr ? JSON.parse(userStr) : null);
  const status = ref('idle');
  const statusLabels = { idle: '空闲', running: '运行中', stopping: '停止中' };

  // Cross-tab communication
  const rerunConfig = ref(null);
  const pendingFilename = ref(null);
  const pendingCompareFilenames = ref(null);
  const refreshFn = ref(null);

  function switchTab(t) {
    if (!isLoggedIn() && t !== 'auth') return;
    router.push(t === 'dashboard' ? '/' : '/' + t);
  }

  function setUser(u, token) {
    user.value = u;
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(u));
  }

  function logout() {
    user.value = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/auth');
  }

  return {
    user, status, statusLabels,
    rerunConfig, pendingFilename, pendingCompareFilenames, refreshFn,
    switchTab, setUser, logout,
  };
});
