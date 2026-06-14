import { describe, it, expect } from 'vitest';
import router from './router';

function findRoute(path) {
  return router.options.routes.find((r) => r.path === path);
}

describe('router 重定向配置', () => {
  it('/ 重定向到 /sites', () => {
    expect(findRoute('/').redirect).toBe('/sites');
  });
  it('/monitor 重定向到 /sites', () => {
    expect(findRoute('/monitor').redirect).toBe('/sites');
  });
  it('/tasks 重定向到 /sites', () => {
    expect(findRoute('/tasks').redirect).toBe('/sites');
  });
  it('/sites 命中 SitesView 路由 (name=sites)', () => {
    expect(findRoute('/sites').name).toBe('sites');
  });
  it('/sites/:id 详情路由保留 (name=site-detail)', () => {
    expect(findRoute('/sites/:id').name).toBe('site-detail');
  });
});
