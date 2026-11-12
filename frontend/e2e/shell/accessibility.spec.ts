import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { compatibleDescriptor, mockDescriptor, type DescriptorMock } from './helpers.ts';

const routes = ['/', '/preferences', '/focus', '/not-a-destination'];
const themes = ['light', 'dark'] as const;
const widths = [1280, 320];

test.describe('axe-core WCAG 2.2 AA scan in both rendered themes (UX-DR04, AC2)', () => {
  for (const theme of themes) {
    for (const width of widths) {
      for (const route of routes) {
        test(`${route} · ${theme} · ${width}px has no axe violations`, async ({ page }) => {
          await page.emulateMedia({ colorScheme: theme });
          await page.setViewportSize({ width, height: 900 });
          await mockDescriptor(page, { json: compatibleDescriptor });
          await page.goto(route);
          await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
          if (route === '/') {
            await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
          }
          const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
          expect(results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`)).toEqual([]);
        });
      }
    }
  }

  const scan = async (page: Page) => {
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
    return results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`);
  };

  const states: { name: string; mock: DescriptorMock; title: string }[] = [
    { name: 'denied (403)', mock: { status: 403 }, title: "This connection isn't available to this session" },
    { name: 'no descriptor (404)', mock: { status: 404 }, title: 'The backend did not publish a compatibility descriptor' },
    { name: 'error (503)', mock: { status: 503 }, title: 'The backend could not be reached' },
    { name: 'incompatible (major 2)', mock: { json: { ...compatibleDescriptor, apiContract: { major: 2, minor: 0 } } }, title: 'Incompatible frontend and backend' },
    { name: 'not a descriptor (200 text/html)', mock: { status: 200, contentType: 'text/html', body: '<!doctype html>' }, title: 'The answer was not a compatibility descriptor' },
  ];
  for (const theme of themes) {
    for (const width of widths) {
      for (const state of states) {
        test(`connection state ${state.name} · ${theme} · ${width}px has no axe violations`, async ({ page }) => {
          await page.emulateMedia({ colorScheme: theme });
          await page.setViewportSize({ width, height: 900 });
          await mockDescriptor(page, state.mock);
          await page.goto('/');
          await expect(page.getByText(state.title)).toBeVisible();
          expect(await scan(page)).toEqual([]);
        });
      }

      test(`offline with stale values · ${theme} · ${width}px has no axe violations`, async ({ page, context }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        await mockDescriptor(page, { json: compatibleDescriptor });
        await page.goto('/');
        await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
        await context.setOffline(true);
        await expect(page.getByText('You are offline')).toBeVisible();
        await expect(page.getByText('Last known values')).toBeVisible();
        expect(await scan(page)).toEqual([]);
      });

      test(`pending "New updates" · ${theme} · ${width}px has no axe violations`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        let version = '0.1.0-SNAPSHOT';
        await page.route('**/api/compatibility', (route) =>
          route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...compatibleDescriptor, backendVersion: version }) }),
        );
        await page.clock.install();
        await page.goto('/');
        await expect(page.getByText('0.1.0-SNAPSHOT')).toBeVisible();
        version = '0.2.0';
        await page.clock.runFor(31_000);
        await expect(page.getByRole('button', { name: 'Show 1 new update' })).toBeVisible();
        expect(await scan(page)).toEqual([]);
      });
    }
  }

  test('the open scope dialog is accessible and traps focus with an inert background', async ({ page }) => {
    await mockDescriptor(page, { json: compatibleDescriptor });
    await page.goto('/');
    await page.getByRole('button', { name: 'Change scope' }).click();
    const dialog = page.getByRole('dialog', { name: 'Choose an authorized project' });
    await expect(dialog).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
    await expect(page.getByRole('heading', { name: 'Choose an authorized project' })).toBeFocused();
    // A native modal keeps page focus inside the dialog; Tab may leave to the browser UI (body),
    // but never reaches an element in the inert background.
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press('Tab');
      const leaked = await page.evaluate(() => {
        const active = document.activeElement;
        return active !== null && active !== document.body && active.closest('dialog') === null;
      });
      expect(leaked, 'focus never reaches the inert background').toBe(false);
    }
    const backgroundInert = await page.evaluate(() => document.querySelector('main')?.closest(':modal') === null);
    expect(backgroundInert).toBe(true);
  });
});
