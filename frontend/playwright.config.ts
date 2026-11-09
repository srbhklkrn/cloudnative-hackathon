import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  expect: { timeout: 20000 },
  testDir: './e2e', fullyParallel: false, workers: 1, timeout: 60000,
  use: { baseURL: process.env.DETOUR_BASE_URL || 'http://127.0.0.1:8080', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
