import { expect, test } from '@playwright/test';
import { compatibleDescriptor, mockDescriptor } from './helpers.ts';

test.describe('keyboard flow, title/focus and return behaviour (AC2, UX-DR40)', () => {
  test.beforeEach(async ({ page }) => {
    await mockDescriptor(page, { json: compatibleDescriptor });
  });

  test('Tab reaches the skip link first and Enter moves focus into main', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'Daily Work' })).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('main')).toBeFocused();
  });

  test('navigating by keyboard updates the title, aria-current and focuses the destination h1', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Daily Work · Owl Mast');
    const focusLink = page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Focus' });
    await focusLink.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/focus$/);
    await expect(page).toHaveTitle('Focus · Owl Mast');
    await expect(page.getByRole('heading', { level: 1, name: 'Focus' })).toBeFocused();
    await expect(focusLink).toHaveAttribute('aria-current', 'page');
    await expect(page.getByText('No assigned work to show')).toBeVisible();
  });

  test('the compact menu is a labelled button that works with the keyboard at 320px', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto('/usage');
    const toggle = page.getByRole('button', { name: /Navigation.*Usage/ });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByRole('link', { name: 'Knowledge' })).toBeHidden();
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Daily Work' })).toBeFocused();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Knowledge' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 1, name: 'Knowledge' })).toBeFocused();
    await expect(page.getByRole('button', { name: /Navigation.*Knowledge/ })).toHaveAttribute('aria-expanded', 'false');
  });

  test('the scope dialog closes on Escape and returns focus to its trigger', async ({ page }) => {
    await page.goto('/');
    const trigger = page.getByRole('button', { name: 'Change scope' });
    await trigger.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Choose an authorized project' });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Choose an authorized project' })).toBeFocused();
    const mainInert = await page.evaluate(() => {
      const main = document.querySelector('main');
      return main ? !main.matches(':modal *') && document.activeElement?.closest('dialog') !== null : false;
    });
    expect(mainInert).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('an unknown address shows the unsupported destination with neutral copy and a working return', async ({ page }) => {
    await page.goto('/');
    await page.goto('/projects/secret-codename');
    await expect(page).toHaveTitle('This destination isn’t available · Owl Mast');
    await expect(page.getByText('secret-codename')).toHaveCount(0);
    await page.getByRole('link', { name: 'Back to Daily Work' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Daily Work' })).toBeFocused();
  });

  test('Back after an in-app navigation returns to the prior destination with its heading focused', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Connections' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Connections' })).toBeFocused();
    await page.goBack();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Daily Work' })).toBeFocused();
  });
});
