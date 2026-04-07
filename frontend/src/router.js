import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/benchmark', name: 'benchmark', component: () => import('./views/BenchmarkView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/schedules', name: 'schedules', component: () => import('./views/SchedulesView.vue') },
    { path: '/config', name: 'config', component: () => import('./views/SettingsView.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
    { path: '/auth', name: 'auth', component: () => import('./views/AuthView.vue') },
    { path: '/admin-users', name: 'admin-users', component: () => import('./views/AdminUsersView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

export default router;
