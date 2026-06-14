import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { setActivePinia, createPinia } from 'pinia';
import { useTimeRangeStore } from '../../stores/timeRange';

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
import { getActiveAlerts, getSitesSummary } from '../../api';
import { toast } from '../../composables/useToast';

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

  it('告警不带 tasks 字段时不崩溃并回退「未命名任务」', async () => {
    vi.mocked(getActiveAlerts).mockResolvedValueOnce({ alerts: [
      { profile: 'siteY', model: 'gpt-4o', streak: 2, task_count: 1 },
    ] });
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('未命名任务');
  });

  it('getSitesSummary 失败时清空站点看板并 toast，不残留过期站点', async () => {
    vi.mocked(getSitesSummary).mockRejectedValueOnce(new Error('boom'));
    // F2 后告警/跑批独立加载，需一并 mock 为空才能落到干净的空态
    const api = await import('../../api');
    vi.mocked(api.getActiveAlerts).mockResolvedValueOnce({ alerts: [] });
    vi.mocked(api.getSchedules).mockResolvedValueOnce({ schedules: [] });
    const w = mountView();
    await flushPromises();
    // 组件正常渲染，未抛未捕获错误
    expect(w.exists()).toBe(true);
    // toast 被调用（错误提示）
    expect(vi.mocked(toast)).toHaveBeenCalled();
    // 落到空态文案
    expect(w.text()).toContain('尚无站点配置');
  });

  it('切换时间范围只重拉看板，不重复请求告警/跑批', async () => {
    const api = await import('../../api');
    const w = mountView();
    await flushPromises();
    const summaryBefore = vi.mocked(api.getSitesSummary).mock.calls.length;
    const alertsBefore = vi.mocked(api.getActiveAlerts).mock.calls.length;
    const schedBefore = vi.mocked(api.getSchedules).mock.calls.length;
    const tr = useTimeRangeStore();
    tr.setHours(tr.hours === 6 ? 24 : 6); // 切到不同值以触发 watch
    await flushPromises();
    expect(vi.mocked(api.getSitesSummary).mock.calls.length).toBe(summaryBefore + 1);
    expect(vi.mocked(api.getActiveAlerts).mock.calls.length).toBe(alertsBefore);
    expect(vi.mocked(api.getSchedules).mock.calls.length).toBe(schedBefore);
  });
});
