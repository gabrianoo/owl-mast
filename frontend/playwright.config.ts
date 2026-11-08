import { defineConfig, devices } from '@playwright/test';

// Shell project: the built shell served by `vite preview`; backend calls are intercepted per test
// (page.route) so every loading/offline/denied/unsupported/incompatible state is exercised without
// a backend. The real-backend smoke lives in playwright.smoke.config.ts.
export default defineConfig({
  testDir: './e2e/shell',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'shell', use: { ...devices['Desktop Chrome'] } }],
  // `vite preview` binds the address `localhost` resolves to first; on the CI runners that is ::1, so
  // a server polled at 127.0.0.1 never answered. The host is pinned to the address polled here, and
  // the preview output is piped so the bound URL appears in the job log.
  webServer: {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173/',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
  },
});
