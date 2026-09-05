import { defineConfig } from '@playwright/test';

/**
 * ⚠️  Needs the Django API running at PUBLIC_API_DOMAIN (see
 *     config/environment.py) with the dev seed applied (devtools/seeds) —
 *     these are end-to-end tests against a real backend, not mocks. Only
 *     the Vite dev server is started automatically here.
 */
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173/static/';

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  retries: 2,
  reporter: 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
