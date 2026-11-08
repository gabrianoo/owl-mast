import { defineConfig, devices } from '@playwright/test';

// Smoke project (OM-01.04-T4): the built shell talks to the real backend started with
// `./gradlew :backend:bootTestRun` (disposable VectorChord container, stub identity issuer). The
// preview server proxies `/api` and `/actuator` to that backend exactly as the ingress/gateway does.
//
// Startup is deterministic: neither server is ever reused (an existing listener on either port fails
// the run instead of silently testing a stale backend), Gradle runs without a daemon so the backend
// JVM stays in the process group Playwright owns, and shutdown sends SIGTERM to that group so Spring
// and Testcontainers stop cleanly instead of being orphaned by the default SIGKILL.
const backendPort = Number(process.env.OWLMAST_SMOKE_BACKEND_PORT ?? '18080');
const backendUrl = `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  testDir: './e2e/smoke',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'smoke', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `cd .. && ./gradlew --no-daemon :backend:bootTestRun --console=plain --args='--server.port=${backendPort}'`,
      url: `${backendUrl}/actuator/health/readiness`,
      reuseExistingServer: false,
      timeout: 600_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 30_000 },
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      // Pinned to the polled address: `localhost` resolves to ::1 first on the CI runners.
      command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4174 --strictPort',
      url: 'http://127.0.0.1:4174/',
      reuseExistingServer: false,
      timeout: 120_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 10_000 },
      stdout: 'pipe',
      env: { OWLMAST_BACKEND_URL: backendUrl },
    },
  ],
});
