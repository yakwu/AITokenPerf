import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/sites', name: 'sites', component: () => import('./views/SitesView.vue') },
    { path: '/sites/:id', name: 'site-detail', component: () => import('./views/SiteDetailView.vue'), props: true },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/tasks', name: 'tasks', component: () => import('./views/TasksView.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
    { path: '/models', name: 'models', component: () => import('./views/ModelsView.vue') },
    { path: '/auth', name: 'auth', component: () => import('./views/AuthView.vue') },
    { path: '/admin-users', name: 'admin-users', component: () => import('./views/AdminUsersView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

export default router;
