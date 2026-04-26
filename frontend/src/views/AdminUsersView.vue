<template>
  <section class="tab-content active">
    <div class="card" style="padding:0;overflow:hidden;margin-bottom:20px">
      <div class="card-header" style="padding:20px 24px 0">
        <div class="card-title">运行监控</div>
        <span class="admin-user-count">{{ runningRuns.length }} 个 Run</span>
      </div>
      <div class="table-wrap" style="border:none;border-radius:0;margin-top:12px">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>用户</th>
              <th>站点</th>
              <th>模型</th>
              <th>Slots</th>
              <th>状态</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in runningRuns" :key="r.run_id">
              <td style="font-family:var(--font-mono);font-size:12px">{{ r.run_id }}</td>
              <td>{{ r.owner_id || '-' }}</td>
              <td>{{ r.profile_name || '-' }}</td>
              <td>{{ runModels(r) }}</td>
              <td>{{ r.requested_slots }}</td>
              <td>{{ r.status }}</td>
              <td><button class="btn btn-ghost btn-sm" @click="stopAdminRun(r.run_id)">停止</button></td>
            </tr>
            <tr v-if="!runsLoading && runningRuns.length === 0">
              <td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:24px">暂无运行中的测试</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card" style="padding:0;overflow:hidden">
      <div class="card-header" style="padding:20px 24px 0">
        <div class="card-title">注册用户</div>
        <span class="admin-user-count">{{ users.length }} 位用户</span>
      </div>
      <div class="table-wrap" style="border:none;border-radius:0;margin-top:12px">
        <table>
          <thead>
            <tr>
              <th style="width:60px">ID</th>
              <th>邮箱</th>
              <th style="width:120px">昵称</th>
              <th style="width:80px">角色</th>
              <th style="width:155px">注册时间</th>
              <th style="width:155px">最后活跃</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.email }}</td>
              <td>{{ u.display_name || '-' }}</td>
              <td>
                <button class="role-badge" :class="u.role" :ref="el => { if (el) roleBtnRefs[u.id] = el }" @click="toggleRoleMenu($event, u.id)">
                  {{ u.role === 'admin' ? '管理员' : '用户' }}
                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
                </button>
              </td>
              <td>{{ formatDate(u.created_at) }}</td>
              <td>{{ formatDate(u.updated_at) }}</td>
              <td>
                <InlineConfirmDelete
                  :active="deleteCandidate === u.id"
                  title="删除用户"
                  @request="deleteCandidate = u.id"
                  @cancel="deleteCandidate = null"
                  @confirm="confirmDelete(u.id)"
                />
              </td>
            </tr>
            <tr v-if="!loading && users.length === 0">
              <td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:32px">暂无用户数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
  <Teleport to="body">
    <div class="role-dropdown-portal" v-if="roleMenuOpen !== null"
      :style="{ position: 'fixed', top: roleMenuPos.top + 'px', left: roleMenuPos.left + 'px', zIndex: 1000 }">
      <div class="role-dropdown">
        <button class="role-option" :class="{ active: users.find(u => u.id === roleMenuOpen)?.role === 'user' }"
          @mousedown.prevent="changeRole(users.find(u => u.id === roleMenuOpen), 'user')">用户</button>
        <button class="role-option" :class="{ active: users.find(u => u.id === roleMenuOpen)?.role === 'admin' }"
          @mousedown.prevent="changeRole(users.find(u => u.id === roleMenuOpen), 'admin')">管理员</button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue';
import { adminStopRunApi, getAdminRuns, getUsers, deleteUserApi, updateUserRoleApi } from '../api';
import { toast } from '../composables/useToast';
import InlineConfirmDelete from '../components/InlineConfirmDelete.vue';

const users = ref([]);
const runningRuns = ref([]);
const loading = ref(false);
const runsLoading = ref(false);
const deleteCandidate = ref(null);
const roleMenuOpen = ref(null);
const roleMenuPos = ref({ top: 0, left: 0 });
const roleBtnRefs = reactive({});

function toggleRoleMenu(e, userId) {
  if (roleMenuOpen.value === userId) {
    roleMenuOpen.value = null;
    return;
  }
  const rect = e.currentTarget.getBoundingClientRect();
  roleMenuPos.value = { top: rect.bottom + 4, left: rect.left };
  roleMenuOpen.value = userId;
}

function closeRoleMenu(e) {
  if (e.target.closest('.role-dropdown-portal')) return;
  roleMenuOpen.value = null;
}

onMounted(() => document.addEventListener('mousedown', closeRoleMenu));
onUnmounted(() => document.removeEventListener('mousedown', closeRoleMenu));

function formatDate(ts) {
  if (!ts) return '-';
  try {
    return new Date(ts + 'Z').toLocaleString('zh-CN');
  } catch { return ts; }
}

async function load() {
  loading.value = true;
  try {
    const res = await getUsers();
    users.value = res.users || [];
  } catch (e) {
    toast('加载失败: ' + e.message, 'error');
  }
  loading.value = false;
}

async function loadRuns() {
  runsLoading.value = true;
  try {
    const res = await getAdminRuns();
    runningRuns.value = res.runs || [];
  } catch (e) {
    toast('加载运行监控失败: ' + e.message, 'error');
  }
  runsLoading.value = false;
}

function runModels(r) {
  const names = (r.tasks || []).map(t => t.model).filter(Boolean);
  return names.length > 2 ? `${names.slice(0, 2).join(', ')} 等 ${names.length} 个` : (names.join(', ') || '-');
}

async function stopAdminRun(id) {
  try {
    await adminStopRunApi(id);
    toast('已发送停止信号', 'info');
    await loadRuns();
  } catch (e) {
    toast('停止失败: ' + e.message, 'error');
  }
}

async function confirmDelete(id) {
  try {
    await deleteUserApi(id);
    toast('已删除', 'info');
    deleteCandidate.value = null;
    await load();
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

async function changeRole(u, newRole) {
  if (u.role === newRole) { roleMenuOpen.value = null; return; }
  try {
    await updateUserRoleApi(u.id, newRole);
    u.role = newRole;
    toast('角色已更新', 'success');
  } catch (e) {
    toast('更新失败: ' + e.message, 'error');
  }
  roleMenuOpen.value = null;
}

let runsTimer = null;
onMounted(() => {
  load();
  loadRuns();
  runsTimer = setInterval(loadRuns, 5000);
});
onUnmounted(() => {
  if (runsTimer) clearInterval(runsTimer);
});
</script>
