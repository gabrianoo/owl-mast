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
