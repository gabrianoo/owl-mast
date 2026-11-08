import { expect, test } from '@playwright/test';

/**
 * OM-01.04-T4 browser-to-backend smoke: the built shell, served by its own preview server, talks
 * to the real backend (`./gradlew :backend:bootTestRun`) through the routing contract. No mocks.
 */
test.describe('browser → real backend smoke (AC4)', () => {
  test('the backend publishes a descriptor the shell reports as compatible', async ({ page }) => {
    const descriptor = await page.request.get('/api/compatibility');
    expect(descriptor.status()).toBe(200);
    const body = (await descriptor.json()) as { service: string; backendVersion: string; apiContract: { major: number; minor: number } };
    expect(body.service).toBe('owl-mast-backend');
    expect(body.apiContract).toEqual({ major: 1, minor: 0 });

    await page.goto('/');
    const panel = page.getByRole('region', { name: 'Workspace connection' });
    await expect(panel.getByText('Compatible frontend and backend')).toBeVisible();
    await expect(panel.getByText(body.backendVersion, { exact: true })).toBeVisible();
    await expect(panel.getByText('1.0', { exact: true })).toBeVisible();
  });

  test('the backend readiness probe answers through the same routing contract', async ({ page }) => {
    const readiness = await page.request.get('/actuator/health/readiness');
    expect(readiness.status()).toBe(200);
    expect(((await readiness.json()) as { status: string }).status).toBe('UP');
  });

  test('unknown API paths come back as problem details, which the shell treats as an error state', async ({ page }) => {
    const missing = await page.request.get('/api/does-not-exist');
    expect(missing.status()).toBe(404);
    expect(missing.headers()['content-type']).toContain('application/problem+json');
  });
});
