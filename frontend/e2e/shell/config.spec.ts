import { expect, test, type Page } from '@playwright/test';
import { compatibleDescriptor } from './helpers.ts';

/**
 * The runtime-config chain end to end: `/owlmast-config.json` -> loadRuntimeConfig -> App ->
 * ApiProvider -> client. `vite preview` has no config endpoint, so it is intercepted here; the image
 * project (e2e/image) covers the endpoint the image really serves.
 */
function recordPaths(page: Page): string[] {
  const paths: string[] = [];
  page.on('request', (request) => paths.push(new URL(request.url()).pathname));
  return paths;
}

test.describe('runtime API prefix (AC4)', () => {
  test('a non-default prefix from the config endpoint is the one the shell calls', async ({ page }) => {
    const paths = recordPaths(page);
    await page.route('**/owlmast-config.json', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ apiPathPrefix: '/owl/api' }) }),
    );
    await page.route(
      (url) => url.pathname === '/owl/api/compatibility',
      (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(compatibleDescriptor) }),
    );
    await page.goto('/');
    await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
    expect(paths).toContain('/owl/api/compatibility');
    expect(paths).not.toContain('/api/compatibility');
  });

  test('a prefix that points at another origin is refused and the default is used', async ({ page }) => {
    const hosts: string[] = [];
    page.on('request', (request) => hosts.push(new URL(request.url()).host));
    const paths = recordPaths(page);
    await page.route('**/owlmast-config.json', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ apiPathPrefix: '//evil.example' }) }),
    );
    await page.route(
      (url) => url.pathname === '/api/compatibility',
      (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(compatibleDescriptor) }),
    );
    await page.goto('/');
    await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
    expect(paths).toContain('/api/compatibility');
    expect(hosts.filter((host) => host.includes('evil.example'))).toEqual([]);
  });
});
