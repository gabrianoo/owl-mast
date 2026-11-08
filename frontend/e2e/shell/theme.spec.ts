import { expect, test } from '@playwright/test';
import { compatibleDescriptor, mockDescriptor, rgb } from './helpers.ts';

test.describe('system theme with explicit override (AC1, UX-DR01)', () => {
  test.beforeEach(async ({ page }) => {
    await mockDescriptor(page, { json: compatibleDescriptor });
  });

  test('follows a dark device theme with the exact dark tokens', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/');
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#0B1018'));
    await expect(page.locator('body')).toHaveCSS('color', rgb('#EAF1FA'));
    await expect(page.locator('.brand svg')).toHaveCSS('color', rgb('#91B5FF'));
    await expect(page.locator('html')).not.toHaveAttribute('data-owl-theme', /.+/);
  });

  test('an explicit Light override saved in Preferences survives reload on a dark device', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/preferences');
    await page.getByRole('radio', { name: 'Light' }).check();
    await expect(page.getByText(/Unsaved change: Light/)).toBeVisible();
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#0B1018'));
    await page.getByRole('button', { name: 'Save theme' }).click();
    await expect(page.getByText('Theme saved: Light.')).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-owl-theme', 'light');
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#F5F7FB'));
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-owl-theme', 'light');
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#F5F7FB'));
    await expect(page.getByText(/Current: Light/)).toBeVisible();
  });

  test('switching back to Follow device removes the override', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('/preferences');
    await page.getByRole('radio', { name: 'Dark' }).check();
    await page.getByRole('button', { name: 'Save theme' }).click();
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#0B1018'));
    await page.getByRole('radio', { name: 'Follow device' }).check();
    await page.getByRole('button', { name: 'Save theme' }).click();
    await expect(page.getByText('Theme saved: Follow device.')).toBeVisible();
    await expect(page.locator('html')).not.toHaveAttribute('data-owl-theme', /.+/);
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#F5F7FB'));
  });
});
