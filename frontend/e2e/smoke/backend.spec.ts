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
    expect(body.apiContract).toEqual({ major: 1, minor: 1 });

    await page.goto('/');
    const panel = page.getByRole('region', { name: 'Workspace connection' });
    await expect(panel.getByText('Compatible frontend and backend')).toBeVisible();
    await expect(panel.getByText(body.backendVersion, { exact: true })).toBeVisible();
    await expect(panel.getByText('1.1', { exact: true })).toBeVisible();
  });

  test('the backend readiness probe answers through the same routing contract', async ({ page }) => {
    const readiness = await page.request.get('/actuator/health/readiness');
    expect(readiness.status()).toBe(200);
    expect(((await readiness.json()) as { status: string }).status).toBe('UP');
  });

  test('an API path asked for without a session is 401 problem details, never a redirect to a login page', async ({ page }) => {
    // OM-02.01: everything below /api except the descriptor and the session read needs a session, an
    // unknown path included (it is 404 only for a signed-in caller).
    const anonymous = await page.request.get('/api/does-not-exist', { maxRedirects: 0 });
    expect(anonymous.status()).toBe(401);
    expect(anonymous.headers()['content-type']).toContain('application/problem+json');
    expect(anonymous.headers().location).toBeUndefined();
    const problem = (await anonymous.json()) as Record<string, unknown>;
    expect(problem.status).toBe(401);
    expect(problem.detail).toBeUndefined();
  });
});
