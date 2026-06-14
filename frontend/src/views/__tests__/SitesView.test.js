import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { setActivePinia, createPinia } from 'pinia';

vi.mock('../../api', () => ({
  api: vi.fn(),
  getSitesSummary: vi.fn(() => Promise.resolve({ summary: [
    { profile: { name: 'siteX', base_url: 'https://x', models: ['gpt-4'] }, health: 'healthy', last_test_at: '20260614_100000' },
  ] })),
  getCellAvailability: vi.fn(() => Promise.resolve({ cells: [] })),
  getActiveAlerts: vi.fn(() => Promise.resolve({ alerts: [
    { profile: 'siteX', model: 'gpt-4', streak: 3, task_count: 1, tasks: [{ id: 1, name: '巡检A' }] },
  ] })),
  getSchedules: vi.fn(() => Promise.resolve({ schedules: [
    { id: 9, name: '每日巡检', profile_ids: ['siteX'], status: 'idle' },
  ] })),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/sites' }),
}));

vi.mock('../../composables/useToast', () => ({ toast: vi.fn() }));

const routerLinkStub = { props: ['to'], template: '<a><slot /></a>' };

import SitesView from '../SitesView.vue';

function mountView() {
  return mount(SitesView, {
    global: {
      stubs: {
        'router-link': routerLinkStub,
        SiteHealthBoard: true,
        ModalOverlay: true,
        ModelSelector: true,
      },
    },
  });
}

describe('SitesView 合并页', () => {
  beforeEach(() => { setActivePinia(createPinia()); });

  it('有告警时渲染告警卡', async () => {
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('siteX × gpt-4');
    expect(w.text()).toContain('连续 3 轮');
  });

  it('健康条显示「告警中」计数', async () => {
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('告警中 1');
  });

  it('跑批状态折叠渲染调度', async () => {
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('监控任务跑批状态（1）');
    expect(w.text()).toContain('每日巡检');
  });
});
