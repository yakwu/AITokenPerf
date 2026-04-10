import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/bench', name: 'bench', component: () => import('./views/TestView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/config', name: 'config', component: () => import('./views/ProfileView.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
    { path: '/models', name: 'models', component: () => import('./views/ModelsView.vue') },
    { path: '/auth', name: 'auth', component: () => import('./views/AuthView.vue') },
    { path: '/admin-users', name: 'admin-users', component: () => import('./views/AdminUsersView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

export default router;
