import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { compatibleDescriptor, mockDescriptor } from './helpers.ts';

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
