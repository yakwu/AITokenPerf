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
                <span class="role-badge" :class="u.role">{{ u.role === 'admin' ? '管理员' : '用户' }}</span>
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
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getUsers, deleteUserApi } from '../api';
import { toast } from '../composables/useToast';
import InlineConfirmDelete from '../components/InlineConfirmDelete.vue';

const users = ref([]);
const loading = ref(false);
const deleteCandidate = ref(null);

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

onMounted(load);
</script>
