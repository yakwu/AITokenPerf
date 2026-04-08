<template>
  <section class="tab-content active">
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
import { getUsers, deleteUserApi, updateUserRoleApi } from '../api';
import { toast } from '../composables/useToast';
import InlineConfirmDelete from '../components/InlineConfirmDelete.vue';

const users = ref([]);
const loading = ref(false);
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

onMounted(load);
</script>
