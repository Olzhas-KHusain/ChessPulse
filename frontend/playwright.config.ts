import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright e2e configuration.
 *
 * Tests run against the full stack from the repository root:
 *   docker compose up --build -d
 * and target the same origin that serves both the API and the built SPA
 * (the FastAPI static mount). Local re-run without Docker:
 *   E2E_BASE_URL=http://127.0.0.1:8000 npx playwright test
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
