import { test as base } from '@playwright/test';
import { SESSION_URL, signedInSession } from './helpers.ts';

/**
 * Shell tests run without a backend. Every page gets a session answer (a signed-in synthetic
 * person) unless the test registers its own with `mockSession`: Playwright consults the route
 * registered last first, so a test's mock wins over this default.
 */
export const test = base.extend<{ defaultSession: undefined }>({
  defaultSession: [
    async ({ page }, use) => {
      await page.route(SESSION_URL, (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(signedInSession) }),
      );
      await use(undefined);
    },
    { auto: true },
  ],
});
