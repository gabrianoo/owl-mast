import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

/**
 * OM-01.04 AC4: the built image in a real browser. Nothing here is served by Vite: the headers,
 * the config endpoint and the misroute answer come from the image's nginx template.
 */
const prefix = process.env.OWLMAST_IMAGE_API_PREFIX ?? '/owl/api';

const descriptor = { service: 'owl-mast-backend', backendVersion: '0.1.0-image', apiContract: { major: 1, minor: 0 } };

interface CspWindow {
  owlmastCspViolations?: string[];
}

/** Records CSP violations (event and console) and uncaught page errors. */
async function watchPage(page: Page): Promise<{ problems: () => Promise<string[]> }> {
  const seen: string[] = [];
  page.on('pageerror', (error) => seen.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error' && /content security policy/i.test(message.text())) seen.push(`console: ${message.text()}`);
  });
  await page.addInitScript(() => {
    const target = window as CspWindow;
    target.owlmastCspViolations = [];
    document.addEventListener('securitypolicyviolation', (event) => {
      target.owlmastCspViolations?.push(`${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  return {
    problems: async () => [...seen, ...(await page.evaluate(() => (window as CspWindow).owlmastCspViolations ?? []))],
  };
}

test.describe('built frontend image in Chromium (production CSP, nginx template, runtime config)', () => {
  test('renders the shell under the production CSP and calls the backend below the configured prefix', async ({ page }) => {
    const watch = await watchPage(page);
    const paths: string[] = [];
    page.on('request', (request) => paths.push(new URL(request.url()).pathname));
    await page.route(`**${prefix}/compatibility`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(descriptor) }),
    );

    const response = await page.goto('/');
    const csp = response?.headers()['content-security-policy'] ?? '';
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("connect-src 'self'");

    await expect(page.getByRole('heading', { level: 1, name: 'Daily Work' })).toBeVisible();
    const panel = page.getByRole('region', { name: 'Workspace connection' });
    await expect(panel.getByText('Compatible frontend and backend')).toBeVisible();
    await expect(panel.getByText('0.1.0-image')).toBeVisible();

    expect(paths).toContain('/owlmast-config.json');
    expect(paths).toContain(`${prefix}/compatibility`);
    if (prefix !== '/api') expect(paths).not.toContain('/api/compatibility');
    expect(await watch.problems()).toEqual([]);
  });

  test('a request below the API prefix that reaches the image is 404, so the shell fails closed', async ({ page }) => {
    const watch = await watchPage(page);
    const misrouted = await page.request.get(`${prefix}/compatibility`);
    expect(misrouted.status()).toBe(404);
    expect(await misrouted.text()).not.toContain('<div id="root">');

    await page.goto('/');
    await expect(page.getByText('The backend did not publish a compatibility descriptor')).toBeVisible();
    await expect(page.getByText(/status 200/)).toHaveCount(0);
    await expect(page.getByText('Compatible frontend and backend')).toHaveCount(0);
    expect(await watch.problems()).toEqual([]);
  });

  test('the pre-paint theme script is allowed by the CSP and app routes fall back to the shell', async ({ page }) => {
    const watch = await watchPage(page);
    await page.emulateMedia({ colorScheme: 'light' });
    await page.addInitScript(() => {
      window.localStorage.setItem('owlmast.theme', 'dark');
    });
    await page.goto('/preferences');
    await expect(page.locator('html')).toHaveAttribute('data-owl-theme', 'dark');
    await expect(page.getByRole('heading', { level: 1, name: 'Preferences' })).toBeVisible();
    await expect(page.getByText(/Current: Dark/)).toBeVisible();
    expect(await watch.problems()).toEqual([]);
  });

  test('the image publishes the API contract this build supports', async ({ page }) => {
    const published = await page.request.get('/api-compatibility.json');
    expect(published.status()).toBe(200);
    expect(published.headers()['content-type']).toContain('application/json');
    const checkout: unknown = JSON.parse(readFileSync(new URL('../../api-compatibility.json', import.meta.url), 'utf8'));
    expect(await published.json()).toEqual(checkout);
  });
});
