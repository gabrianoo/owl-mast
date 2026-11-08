import { defineConfig, devices } from '@playwright/test';

// Smoke project (OM-01.04-T4): the built shell talks to the real backend started with
// `./gradlew :backend:bootTestRun` (disposable VectorChord container, stub identity issuer). The
// preview server proxies `/api` and `/actuator` to that backend exactly as the ingress/gateway does.
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
      command: `cd .. && ./gradlew :backend:bootTestRun --console=plain --args='--server.port=${backendPort}'`,
      url: `${backendUrl}/actuator/health/readiness`,
      reuseExistingServer: !process.env.CI,
      timeout: 600_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: 'npm run build && npm run preview -- --port 4174 --strictPort',
      url: 'http://127.0.0.1:4174/',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { OWLMAST_BACKEND_URL: backendUrl },
    },
  ],
});
