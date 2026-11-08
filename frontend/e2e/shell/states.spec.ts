import { expect, test } from '@playwright/test';
import { compatibleDescriptor, mockDescriptor } from './helpers.ts';

test.describe('connection states: loading, compatible, incompatible, unsupported, denied, error, offline (AC3/AC4)', () => {
  test('compatible pair shows backend and frontend facts', async ({ page }) => {
    await mockDescriptor(page, { json: compatibleDescriptor });
    await page.goto('/');
    const panel = page.getByRole('region', { name: 'Workspace connection' });
    await expect(panel.getByText('Compatible frontend and backend')).toBeVisible();
    await expect(panel.getByText('0.1.0-SNAPSHOT')).toBeVisible();
    await expect(panel.getByText(/Checked at/)).toBeVisible();
  });

  test('a different major is reported as unsupported with both contracts named', async ({ page }) => {
    await mockDescriptor(page, { json: { ...compatibleDescriptor, apiContract: { major: 2, minor: 3 } } });
    await page.goto('/');
    await expect(page.getByText('Incompatible frontend and backend')).toBeVisible();
    await expect(page.getByText(/1\.x.*publishes 2\.3/)).toBeVisible();
  });

  test('a backend without a descriptor fails closed as unsupported', async ({ page }) => {
    await mockDescriptor(page, { status: 404 });
    await page.goto('/');
    await expect(page.getByText('The backend did not publish a compatibility descriptor')).toBeVisible();
  });

  test('denied access shows neutral copy and moves focus to it', async ({ page }) => {
    await mockDescriptor(page, { status: 403 });
    await page.goto('/');
    const heading = page.getByRole('heading', { level: 3, name: "This connection isn't available to this session" });
    await expect(heading).toBeVisible();
    await expect(heading).toBeFocused();
    await expect(page.getByText('mocked')).toHaveCount(0);
  });

  test('a server error is a distinct problem state without invented values', async ({ page }) => {
    await mockDescriptor(page, { status: 503, body: JSON.stringify({ status: 503, title: 'Service Unavailable', detail: 'db://user:pw@host' }) });
    await page.goto('/');
    await expect(page.getByText('The backend could not be reached')).toBeVisible();
    await expect(page.getByText(/status 503/)).toBeVisible();
    await expect(page.getByText(/user:pw/)).toHaveCount(0);
    await expect(page.getByText('Compatible frontend and backend')).toHaveCount(0);
  });

  test('loading is labelled text without placeholder numbers', async ({ page }) => {
    await page.route('**/api/compatibility', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(compatibleDescriptor) });
    });
    await page.goto('/');
    const panel = page.getByRole('region', { name: 'Workspace connection' });
    await expect(panel.getByText('Checking the backend connection')).toBeVisible();
    await expect(panel.locator('[role="progressbar"]')).toHaveCount(0);
    await expect(panel.getByText('Compatible frontend and backend')).toBeVisible();
  });

  test('going offline requests nothing new, labels earlier values stale, and reconnecting re-checks', async ({ page, context }) => {
    const descriptor = await mockDescriptor(page, { json: compatibleDescriptor });
    await page.goto('/');
    await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
    const before = descriptor.hits();
    await context.setOffline(true);
    await expect(page.getByText('You are offline')).toBeVisible();
    await expect(page.getByText('Last known values')).toBeVisible();
    await page.waitForTimeout(500);
    expect(descriptor.hits()).toBe(before);
    await context.setOffline(false);
    await expect(page.getByText('You are offline')).toBeHidden();
    await expect.poll(() => descriptor.hits()).toBeGreaterThan(before);
    await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
  });

  test('a changed re-check waits behind "New updates" and applying it focuses the section', async ({ page }) => {
    let version = '0.1.0-SNAPSHOT';
    await page.route('**/api/compatibility', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...compatibleDescriptor, backendVersion: version }) }),
    );
    await page.clock.install();
    await page.goto('/');
    await expect(page.getByText('0.1.0-SNAPSHOT')).toBeVisible();
    version = '0.2.0';
    await page.clock.runFor(31_000);
    await expect(page.getByText('0.1.0-SNAPSHOT')).toBeVisible();
    await expect(page.getByText(/1 new update available/)).toBeVisible();
    await page.getByRole('button', { name: 'Show 1 new update' }).click();
    await expect(page.getByText('0.2.0')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Workspace connection' })).toBeFocused();
  });
});
