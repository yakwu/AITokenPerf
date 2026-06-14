import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import SiteHealthBoard from '../SiteHealthBoard.vue';

// router-link stub：渲染默认插槽内容（站点名），避免空占位丢失文本
const routerLinkStub = {
  props: ['to'],
  template: '<a><slot /></a>',
};

const sites = [{
  profile: { name: 'siteX', base_url: 'https://api.x.com', models: ['gpt-4'] },
  health: 'error', last_test_at: '20260614_100000',
}];

describe('SiteHealthBoard', () => {
  it('渲染站点行', () => {
    const w = mount(SiteHealthBoard, {
      props: { sites, availabilityLut: {}, buckets: 24, favorites: new Set() },
      global: { stubs: { 'router-link': routerLinkStub } },
    });
    expect(w.text()).toContain('siteX');
  });

  it('点一键测试时 emit test-site，payload 是 site 对象', async () => {
    const w = mount(SiteHealthBoard, {
      props: { sites, availabilityLut: {}, buckets: 24, favorites: new Set() },
      global: { stubs: { 'router-link': routerLinkStub } },
    });
    await w.find('.row-actions .btn-ghost').trigger('click');
    expect(w.emitted('test-site')).toBeTruthy();
    expect(w.emitted('test-site')[0][0]).toEqual(sites[0]);
  });

  it('点收藏时 emit toggle-favorite，payload 是站点名', async () => {
    const w = mount(SiteHealthBoard, {
      props: { sites, availabilityLut: {}, buckets: 24, favorites: new Set() },
      global: { stubs: { 'router-link': routerLinkStub } },
    });
    await w.find('.fav').trigger('click');
    expect(w.emitted('toggle-favorite')).toBeTruthy();
    expect(w.emitted('toggle-favorite')[0][0]).toBe('siteX');
  });
});
