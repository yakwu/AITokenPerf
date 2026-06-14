import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/sites' },
    { path: '/sites', name: 'sites', component: () => import('./views/SitesView.vue') },
    { path: '/sites/:id', name: 'site-detail', component: () => import('./views/SiteDetailView.vue'), props: true },
    { path: '/monitor', redirect: '/sites' },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/tasks', redirect: '/sites' },
    {
      path: '/settings',
      component: () => import('./views/SettingsHub.vue'),
      children: [
        { path: '', redirect: '/settings/notifiers' },
        { path: 'notifiers', name: 'settings-notifiers', component: () => import('./views/NotifiersView.vue') },
        { path: 'models', name: 'settings-models', component: () => import('./views/ModelsView.vue') },
        { path: 'users', name: 'settings-users', component: () => import('./views/AdminUsersView.vue') },
        { path: 'profile', name: 'settings-profile', component: () => import('./views/SettingsView.vue') },
      ],
    },
    { path: '/config', redirect: '/sites' },
    { path: '/auth', name: 'auth', component: () => import('./views/AuthView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

router.beforeEach((to) => {
  if (to.path === '/auth') return;
  const userStr = localStorage.getItem('user');
  if (!userStr) return;
  try {
    const user = JSON.parse(userStr);
    if (user.must_change_password) return '/auth';
    if ((to.path.startsWith('/settings/users') || to.path.startsWith('/settings/models'))
        && user.role !== 'admin') {
      return '/settings/notifiers';
    }
  } catch {}
});

export default router;
