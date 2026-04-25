import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 0,
  reporter: 'list',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://localhost:5181',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: [
    {
      command: '.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8081',
      port: 8081,
      reuseExistingServer: !process.env.CI,
      timeout: 15000,
      env: {
        DATABASE_URL: 'sqlite+aiosqlite:///tmp/e2e-test.db',
        E2E_TEST_MODE: '1',
        JWT_SECRET: 'e2e-test-secret',
        LOG_MODE: 'stdout',
        CORS_ORIGINS: 'http://localhost:5181',
      },
    },
    {
      command: 'bun run dev --port 5181',
      port: 5181,
      reuseExistingServer: !process.env.CI,
      timeout: 15000,
      cwd: './frontend',
      env: {
        VITE_PROXY_TARGET: 'http://localhost:8081',
      },
    },
  ],
});
