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

/** A Content-Security-Policy header as directive name -> sources, so a widened policy cannot pass as a substring. */
function parseCsp(header: string): Record<string, string[]> {
  const directives: Record<string, string[]> = {};
  for (const part of header.split(';')) {
    const [rawName, ...sources] = part.trim().split(/\s+/);
    if (!rawName) continue;
    const name = rawName.toLowerCase();
    // A browser honours the first occurrence only; a repeated directive is a different policy.
    expect(Object.hasOwn(directives, name), `directive ${name} appears twice`).toBe(false);
    directives[name] = sources;
  }
  return directives;
}

/** The whole production policy (frontend/nginx/owlmast-headers.conf): any added source or dropped directive fails. */
const PRODUCTION_CSP: Record<string, string[]> = {
  'default-src': ["'self'"],
  'script-src': ["'self'"],
  'style-src': ["'self'", "'unsafe-inline'"],
  'img-src': ["'self'", 'data:'],
  'font-src': ["'self'"],
  'connect-src': ["'self'"],
  'base-uri': ["'self'"],
  'form-action': ["'self'"],
  'frame-ancestors': ["'none'"],
  'object-src': ["'none'"],
};

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
    const headers = (await response?.headersArray()) ?? [];
    const policies = headers.filter((header) => header.name.toLowerCase() === 'content-security-policy');
    // Exactly one policy header with exactly these directives: a second header, 'unsafe-inline',
    // 'unsafe-eval', '*' or an extra origin in any directive is a different policy.
    expect(policies).toHaveLength(1);
    expect(parseCsp(policies[0]?.value ?? '')).toEqual(PRODUCTION_CSP);
    expect(headers.filter((header) => header.name.toLowerCase() === 'content-security-policy-report-only')).toEqual([]);

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

  test('every answer the image gives carries the production policy, including the manifest and the misroute 404s', async ({ page }) => {
    const shell = await (await page.request.get('/')).text();
    const asset = /\/assets\/[^"]+\.js/.exec(shell)?.[0] ?? '';
    expect(asset).not.toBe('');
    const expected: [string, number, string][] = [
      ['/', 200, 'no-store'],
      ['/focus', 200, 'no-store'],
      ['/owlmast-config.json', 200, 'no-store'],
      ['/api-compatibility.json', 200, 'no-store'],
      [prefix, 404, 'no-store'],
      [`${prefix}/compatibility`, 404, 'no-store'],
      [asset, 200, 'public, max-age=31536000, immutable'],
      // Not the asset policy: a 404 kept for a year would outlive the rolling update that caused it.
      ['/assets/missing.js', 404, 'no-store'],
    ];
    for (const [path, status, cacheControl] of expected) {
      const answer = await page.request.get(path);
      const headers = answer.headers();
      expect(answer.status(), path).toBe(status);
      expect(parseCsp(headers['content-security-policy'] ?? ''), path).toEqual(PRODUCTION_CSP);
      expect(headers['content-security-policy-report-only'], path).toBeUndefined();
      expect(headers['x-content-type-options'], path).toBe('nosniff');
      expect(headers['x-frame-options'], path).toBe('DENY');
      expect(headers['referrer-policy'], path).toBe('same-origin');
      expect(headers['cache-control'], path).toBe(cacheControl);
    }
  });

  test('an unsatisfiable range is a 416 with every header once, and hashed assets are always sent whole', async ({ page }) => {
    // nginx adds the headers before its range filter and again for the error answer; the template
    // sends the 416 from a location that adds nothing, and keeps ranges off under /assets/, where
    // the immutable policy is already written when the range turns out to be unsatisfiable.
    const once = ['content-security-policy', 'x-content-type-options', 'x-frame-options', 'referrer-policy', 'cache-control'];
    const count = (headers: { name: string; value: string }[], name: string) => headers.filter((header) => header.name.toLowerCase() === name).length;
    for (const path of ['/', '/focus', '/theme-boot.js', '/api-compatibility.json']) {
      const unsatisfiable = await page.request.get(path, { headers: { Range: 'bytes=999999999-' } });
      expect(unsatisfiable.status(), path).toBe(416);
      const headers = unsatisfiable.headersArray();
      for (const name of once) expect(count(headers, name), `${path} ${name}`).toBe(1);
      expect(parseCsp(unsatisfiable.headers()['content-security-policy'] ?? ''), path).toEqual(PRODUCTION_CSP);
      expect(unsatisfiable.headers()['cache-control'], path).toBe('no-store');
      expect(unsatisfiable.headers()['content-range'], path).toMatch(/^bytes \*\/\d+$/);

      const partial = await page.request.get(path, { headers: { Range: 'bytes=0-9' } });
      expect(partial.status(), path).toBe(206);
      for (const name of once) expect(count(partial.headersArray(), name), `${path} ${name}`).toBe(1);
      expect(partial.headers()['cache-control'], path).toBe('no-store');
      expect((await partial.body()).length, path).toBe(10);
    }

    // One range per request (max_ranges 1): several are answered whole, so there is no multipart answer.
    const several = await page.request.get('/theme-boot.js', { headers: { Range: 'bytes=0-1,3-4' } });
    expect(several.status()).toBe(200);
    for (const name of once) expect(count(several.headersArray(), name), name).toBe(1);
    expect(several.headers()['content-type']).not.toContain('multipart');

    const shell = await (await page.request.get('/')).text();
    const asset = /\/assets\/[^"]+\.js/.exec(shell)?.[0] ?? '';
    expect(asset).not.toBe('');
    for (const range of ['bytes=999999999-', 'bytes=0-9']) {
      const answer = await page.request.get(asset, { headers: { Range: range } });
      expect(answer.status(), range).toBe(200);
      for (const name of once) expect(count(answer.headersArray(), name), `${range} ${name}`).toBe(1);
      expect(answer.headers()['cache-control'], range).toBe('public, max-age=31536000, immutable');
      expect(answer.headers()['content-range'], range).toBeUndefined();
    }
  });

  test('the image publishes the API contract this build supports', async ({ page }) => {
    const published = await page.request.get('/api-compatibility.json');
    expect(published.status()).toBe(200);
    expect(published.headers()['content-type']).toContain('application/json');
    const checkout: unknown = JSON.parse(readFileSync(new URL('../../api-compatibility.json', import.meta.url), 'utf8'));
    expect(await published.json()).toEqual(checkout);
  });
});
