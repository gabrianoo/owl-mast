import { expect, test } from '@playwright/test';
import { compatibleDescriptor, expectControlTargets, expectNoHorizontalOverflow, mockDescriptor, rgb } from './helpers.ts';

test.describe('responsive layout, 320px reflow, 200% text zoom, 44px targets, reduced motion (AC1/AC2)', () => {
  test.beforeEach(async ({ page }) => {
    await mockDescriptor(page, { json: compatibleDescriptor });
  });

  for (const route of ['/', '/preferences']) {
    test(`${route} reflows at 320px without horizontal scrolling and keeps 44px controls`, async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 700 });
      await page.goto(route);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await page.getByRole('button', { name: /Navigation/ }).click();
      await expectNoHorizontalOverflow(page);
      await expectControlTargets(page);
      await expect(page.getByText('Project', { exact: true })).toBeVisible();
      await expect(page.getByText('Period', { exact: true })).toBeVisible();
    });
  }

  test('200% text size keeps the shell readable with no horizontal overflow at a laptop width', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '200%';
    });
    await expect(page.getByRole('heading', { level: 1, name: 'Daily Work' })).toBeVisible();
    const h1Size = await page.getByRole('heading', { level: 1 }).evaluate((element) => parseFloat(getComputedStyle(element).fontSize));
    expect(h1Size).toBeCloseTo(56, 0);
    await expectNoHorizontalOverflow(page);
    await expectControlTargets(page);
  });

  for (const width of [320, 640]) {
    test(`${width}px with 200% text: the compact menu and the scope dialog stay usable and return focus`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/');
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '200%';
      });
      await expect(page.getByRole('heading', { level: 1, name: 'Daily Work' })).toBeVisible();
      await expect(page).toHaveTitle('Daily Work · Owl Mast');
      await expectNoHorizontalOverflow(page);

      const toggle = page.getByRole('button', { name: /Navigation.*Daily Work/ });
      await toggle.focus();
      await page.keyboard.press('Enter');
      await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      await expect(page.getByRole('link', { name: 'Knowledge' })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await expectControlTargets(page);
      await page.keyboard.press('Escape');
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await expect(toggle).toBeFocused();

      const trigger = page.getByRole('button', { name: 'Change scope' });
      await trigger.focus();
      await page.keyboard.press('Enter');
      const dialog = page.getByRole('dialog', { name: 'Choose an authorized project' });
      await expect(dialog).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Choose an authorized project' })).toBeFocused();
      const box = await dialog.boundingBox();
      expect(box, 'dialog is laid out').not.toBeNull();
      expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width + 0.5);
      const closeBox = await dialog.getByRole('button', { name: 'Close' }).boundingBox();
      expect(closeBox?.height ?? 0).toBeGreaterThanOrEqual(43.5);
      expect(closeBox?.width ?? 0).toBeGreaterThanOrEqual(43.5);
      await expectNoHorizontalOverflow(page);
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(trigger).toBeFocused();

      // Navigation under enlarged text still moves the title and focus (AC2).
      await toggle.click();
      await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Focus' }).click();
      await expect(page).toHaveTitle('Focus · Owl Mast');
      await expect(page.getByRole('heading', { level: 1, name: 'Focus' })).toBeFocused();
      await expectNoHorizontalOverflow(page);
    });
  }

  test('wide layout shows the persistent rail; compact layout shows the labelled menu', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');
    await expect(page.getByRole('button', { name: /Navigation/ })).toHaveCount(0);
    await expect(page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Usage' })).toBeVisible();
    await page.setViewportSize({ width: 800, height: 800 });
    await expect(page.getByRole('button', { name: /Navigation.*Daily Work/ })).toBeVisible();
  });

  test('exact light tokens render on the page and the title uses 28px/650 at wide widths', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');
    await expect(page.locator('body')).toHaveCSS('background-color', rgb('#F5F7FB'));
    await expect(page.locator('body')).toHaveCSS('color', rgb('#172337'));
    const h1 = page.getByRole('heading', { level: 1 });
    await expect(h1).toHaveCSS('font-size', '28px');
    await expect(h1).toHaveCSS('font-weight', '650');
    await expect(page.locator('.brand svg')).toHaveCSS('color', rgb('#2456D6'));
    const focusRing = page.getByRole('button', { name: 'Change scope' });
    await focusRing.focus();
    await expect(focusRing).toHaveCSS('outline-width', '3px');
    await expect(focusRing).toHaveCSS('outline-offset', '2px');
    await expect(focusRing).toHaveCSS('outline-color', rgb('#74849B'));
  });

  test('reduced motion disables transitions and animations', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    const durations = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('a, button, .state-message, .nav__link')].map((element) => {
        const style = getComputedStyle(element);
        return { transition: parseFloat(style.transitionDuration), animation: parseFloat(style.animationDuration) };
      }),
    );
    for (const duration of durations) {
      expect(duration.transition).toBeLessThanOrEqual(0.001);
      expect(duration.animation).toBeLessThanOrEqual(0.001);
    }
  });
});
