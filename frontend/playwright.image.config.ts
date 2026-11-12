import { defineConfig, devices } from '@playwright/test';

// Image project (OM-01.04 AC4): Chromium against the built frontend image itself, so the production
// Content-Security-Policy, the nginx template and `/owlmast-config.json` are exercised in a browser
// (the shell and smoke projects use `vite preview`, which serves none of them). The container is
// started by scripts/verify-frontend-artifact.sh, which passes its address and API prefix here.
const baseURL = process.env.OWLMAST_IMAGE_BASE_URL;
if (!baseURL) {
  throw new Error('OWLMAST_IMAGE_BASE_URL is required: run scripts/verify-frontend-artifact.sh with OWLMAST_IMAGE_BROWSER_SMOKE=1');
}

export default defineConfig({
  testDir: './e2e/image',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  timeout: 30_000,
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [{ name: 'image', use: { ...devices['Desktop Chrome'] } }],
});
