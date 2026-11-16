import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';
import {
  SIGN_OUT_URL,
  compatibleDescriptor,
  expectControlTargets,
  expectNoHorizontalOverflow,
  mockDescriptor,
  mockSession,
  signedInSession,
  signedOutSession,
  syntheticCsrf,
  type SessionMock,
} from './helpers.ts';
import { test } from './test.ts';

const SIGN_IN_URL = '**/api/session/sign-in';

/** Stands in for the backend's redirect to the identity provider: records the navigation and answers a blank page. */
async function recordSignInNavigations(page: Page): Promise<() => number> {
  let navigations = 0;
  await page.route(SIGN_IN_URL, (route) => {
    navigations += 1;
    return route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>identity provider stand-in</title>' });
  });
  return () => navigations;
}

async function scan(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
  return results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`);
}

test.describe('session states: signed out, signed in, expired, sign-in failed, provider error, sign out (OM-02.01)', () => {
  test.beforeEach(async ({ page }) => {
    await mockDescriptor(page, { json: compatibleDescriptor });
  });

  test('signed out: destinations show the signed-out state and the sign-in action leaves for the sign-in endpoint', async ({ page }) => {
    await mockSession(page, { json: signedOutSession });
    const navigations = await recordSignInNavigations(page);
    await page.goto('/focus');
    const main = page.getByRole('main');
    await expect(main.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await expect(main.getByText('No assigned work to show')).toHaveCount(0);
    await expect(page.getByRole('group', { name: 'Session' }).getByText('Signed out')).toBeVisible();
    await main.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL('**/api/session/sign-in');
    expect(navigations()).toBe(1);
  });

  test('signed out: the public connection panel and Preferences stay usable', async ({ page }) => {
    await mockSession(page, { json: signedOutSession });
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await expect(page.getByText('Compatible frontend and backend')).toBeVisible();
    await page.getByRole('link', { name: 'Preferences' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Preferences' })).toBeFocused();
    await expect(page.getByText('You are signed out')).toHaveCount(0);
  });

  test('signed in: the header names the person and the destination content is shown', async ({ page }) => {
    await mockSession(page, { json: signedInSession });
    await page.goto('/focus');
    const session = page.getByRole('group', { name: 'Session' });
    await expect(session.getByText('Signed in as Ada Synthetic')).toBeVisible();
    await expect(session.getByRole('button', { name: 'Sign out' })).toBeVisible();
    await expect(session.getByRole('button', { name: 'Sign in' })).toHaveCount(0);
    await expect(page.getByText('No assigned work to show')).toBeVisible();
    await expect(page.getByText(/not part of this version of the shell/)).toHaveCount(0);
  });

  test('expired: a later session read that says signed out removes the content and offers sign-in', async ({ page }) => {
    const session = await mockSession(page, { json: signedInSession });
    await page.clock.install();
    await page.goto('/focus');
    await expect(page.getByText('No assigned work to show')).toBeVisible();
    session.set({ json: signedOutSession });
    await page.clock.runFor(61_000);
    const heading = page.getByRole('heading', { level: 2, name: 'Your session ended' });
    await expect(heading).toBeVisible();
    await expect(heading).toBeFocused();
    await expect(page.getByText('No assigned work to show')).toHaveCount(0);
    await expect(page.getByRole('main').getByRole('button', { name: 'Sign in again' })).toBeVisible();
    await expect(page.getByRole('group', { name: 'Session' }).getByRole('button', { name: 'Sign out' })).toHaveCount(0);
  });

  test('a session endpoint that fails is a problem state with a retry, never signed in and never pending', async ({ page }) => {
    const session = await mockSession(page, { status: 503 });
    await page.goto('/focus');
    await expect(page.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeVisible();
    await expect(page.getByText('mocked')).toHaveCount(0);
    await expect(page.getByText('No assigned work to show')).toHaveCount(0);
    session.set({ json: signedInSession });
    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByText('No assigned work to show')).toBeVisible();
  });

  test('sign-in failed: a denied state, the parameter leaves the address, sign-in can be tried again', async ({ page }) => {
    await mockSession(page, { json: signedOutSession });
    const navigations = await recordSignInNavigations(page);
    await page.goto('/?sign-in=failed');
    const main = page.getByRole('main');
    await expect(main.getByRole('heading', { level: 2, name: 'Sign-in was not completed' })).toBeVisible();
    await expect(main.locator('.state-message[data-kind="denied"]')).toHaveCount(1);
    expect(new URL(page.url()).search).toBe('');
    await main.getByRole('button', { name: 'Sign in again' }).click();
    await page.waitForURL('**/api/session/sign-in');
    expect(navigations()).toBe(1);
  });

  test('provider error: a distinct error state whose retry starts sign-in again', async ({ page }) => {
    await mockSession(page, { json: signedOutSession });
    const navigations = await recordSignInNavigations(page);
    await page.goto('/?sign-in=unavailable');
    const main = page.getByRole('main');
    await expect(main.getByRole('heading', { level: 2, name: 'The identity provider is unavailable' })).toBeVisible();
    await expect(main.getByText('You are signed out')).toHaveCount(0);
    await expect(main.getByText('Sign-in was not completed')).toHaveCount(0);
    expect(new URL(page.url()).search).toBe('');
    await page.reload();
    // The parameter is gone, so a reload shows the plain signed-out state instead of repeating the error.
    await expect(main.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await page.goto('/?sign-in=unavailable');
    await main.getByRole('button', { name: 'Retry sign-in' }).click();
    await page.waitForURL('**/api/session/sign-in');
    expect(navigations()).toBe(1);
  });

  test('sign out sends the CSRF header with the session cookie only and returns the shell to signed out', async ({ page }) => {
    const session = await mockSession(page, { json: signedInSession });
    const calls: { method: string; csrf: string | undefined; authorization: string | undefined }[] = [];
    await page.route(SIGN_OUT_URL, (route) => {
      const request = route.request();
      calls.push({
        method: request.method(),
        csrf: request.headers()[syntheticCsrf.headerName.toLowerCase()],
        authorization: request.headers().authorization,
      });
      session.set({ json: signedOutSession });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ state: 'signed-out', identityProvider: 'ended' }) });
    });
    await page.goto('/focus');
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await expect(page.getByText('No assigned work to show')).toHaveCount(0);
    await expect(page.getByRole('group', { name: 'Session' }).getByRole('button', { name: 'Sign in' })).toBeVisible();
    expect(calls).toEqual([{ method: 'POST', csrf: syntheticCsrf.token, authorization: undefined }]);
    // Nothing about the session is kept where a script could read it.
    expect(await page.evaluate(() => ({ local: window.localStorage.length, session: window.sessionStorage.length, cookie: document.cookie }))).toEqual({
      local: 0,
      session: 0,
      cookie: '',
    });
  });

  test('sign out says so when the identity provider session could not be confirmed as ended', async ({ page }) => {
    const session = await mockSession(page, { json: signedInSession });
    await page.route(SIGN_OUT_URL, (route) => {
      session.set({ json: signedOutSession });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ state: 'signed-out', identityProvider: 'unconfirmed' }) });
    });
    await page.goto('/focus');
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByText(/could not confirm that the identity provider ended its own/)).toBeVisible();
  });

  test('session not confirmed after signed in (identity provider outage): Sign out stays, carries the CSRF header and ends the session', async ({ page }) => {
    const session = await mockSession(page, { json: signedInSession });
    const calls: { method: string; csrf: string | undefined }[] = [];
    await page.route(SIGN_OUT_URL, (route) => {
      const request = route.request();
      calls.push({ method: request.method(), csrf: request.headers()[syntheticCsrf.headerName.toLowerCase()] });
      session.set({ json: signedOutSession });
      // The backend ends its session during the outage and cannot confirm the identity provider's.
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ state: 'signed-out', identityProvider: 'unconfirmed' }) });
    });
    await page.clock.install();
    await page.goto('/focus');
    await expect(page.getByText('No assigned work to show')).toBeVisible();
    // The backend can no longer ask the identity provider whether the session stands: 503.
    session.set({ status: 503 });
    await page.clock.runFor(61_000);
    await expect(page.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeVisible();
    await expect(page.getByText('No assigned work to show')).toHaveCount(0);
    const control = page.getByRole('group', { name: 'Session' });
    await expect(control.getByText('Session not confirmed')).toBeVisible();
    await expect(control.getByText('Ada Synthetic')).toHaveCount(0);
    await control.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await expect(page.getByText(/could not confirm that the identity provider ended its own/)).toBeVisible();
    await expect(control.getByRole('button', { name: 'Sign out' })).toHaveCount(0);
    expect(calls).toEqual([{ method: 'POST', csrf: syntheticCsrf.token }]);
  });

  test('session not confirmed after signed in: a sign-out that fails is reported and stays offered', async ({ page }) => {
    const session = await mockSession(page, { json: signedInSession });
    await page.route(SIGN_OUT_URL, (route) =>
      route.fulfill({ status: 503, contentType: 'application/problem+json', body: JSON.stringify({ status: 503, title: 'mocked' }) }),
    );
    await page.clock.install();
    await page.goto('/focus');
    await expect(page.getByText('No assigned work to show')).toBeVisible();
    session.set({ status: 503 });
    await page.clock.runFor(61_000);
    const control = page.getByRole('group', { name: 'Session' });
    await control.getByRole('button', { name: 'Sign out' }).click();
    await expect(control.getByText('Sign-out could not be confirmed')).toBeVisible();
    await expect(control.getByText('Session not confirmed')).toBeVisible();
    await expect(control.getByRole('button', { name: 'Sign out' })).toBeVisible();
    await expect(page.getByText('mocked')).toHaveCount(0);
  });

  test('a shell that starts during an identity provider outage with a kept session: Sign out is offered, carries the CSRF header of the 503 and ends the session (R2-3)', async ({ page }) => {
    // The backend keeps a session for this browser and cannot confirm it: 503 with the CSRF token.
    const session = await mockSession(page, { status: 503, csrf: syntheticCsrf });
    const calls: { method: string; csrf: string | undefined; authorization: string | undefined }[] = [];
    await page.route(SIGN_OUT_URL, (route) => {
      const request = route.request();
      calls.push({
        method: request.method(),
        csrf: request.headers()[syntheticCsrf.headerName.toLowerCase()],
        authorization: request.headers().authorization,
      });
      session.set({ json: signedOutSession });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ state: 'signed-out', identityProvider: 'unconfirmed' }) });
    });
    await page.goto('/focus');
    await expect(page.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeVisible();
    await expect(page.getByText('No assigned work to show')).toHaveCount(0);
    await expect(page.getByText('mocked')).toHaveCount(0);
    const control = page.getByRole('group', { name: 'Session' });
    await expect(control.getByText('Session not confirmed')).toBeVisible();
    await expect(control.getByText('Ada Synthetic')).toHaveCount(0);
    await control.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await expect(page.getByText(/could not confirm that the identity provider ended its own/)).toBeVisible();
    await expect(control.getByRole('button', { name: 'Sign out' })).toHaveCount(0);
    expect(calls).toEqual([{ method: 'POST', csrf: syntheticCsrf.token, authorization: undefined }]);
    // The token is held in memory only.
    expect(await page.evaluate(() => ({ local: window.localStorage.length, session: window.sessionStorage.length, cookie: document.cookie }))).toEqual({
      local: 0,
      session: 0,
      cookie: '',
    });
  });

  test('a shell that starts during the outage: a sign-out that fails is reported and stays offered', async ({ page }) => {
    await mockSession(page, { status: 503, csrf: syntheticCsrf });
    await page.route(SIGN_OUT_URL, (route) =>
      route.fulfill({ status: 503, contentType: 'application/problem+json', body: JSON.stringify({ status: 503, title: 'mocked' }) }),
    );
    await page.goto('/focus');
    const control = page.getByRole('group', { name: 'Session' });
    await control.getByRole('button', { name: 'Sign out' }).click();
    await expect(control.getByText('Sign-out could not be confirmed')).toBeVisible();
    await expect(control.getByText('Session not confirmed')).toBeVisible();
    await expect(control.getByRole('button', { name: 'Sign out' })).toBeVisible();
    await expect(page.getByText('mocked')).toHaveCount(0);
  });

  test('a session endpoint that fails without a csrf member before anybody was signed in offers no sign-out', async ({ page }) => {
    await mockSession(page, { status: 503 });
    await page.goto('/focus');
    const control = page.getByRole('group', { name: 'Session' });
    await expect(control.getByText('Session not confirmed')).toBeVisible();
    await expect(control.getByRole('button', { name: 'Sign out' })).toHaveCount(0);
  });

  test('a refused sign-out (403 twice) is reported and the person stays signed in', async ({ page }) => {
    await mockSession(page, { json: signedInSession });
    let attempts = 0;
    await page.route(SIGN_OUT_URL, (route) => {
      attempts += 1;
      return route.fulfill({ status: 403, contentType: 'application/problem+json', body: JSON.stringify({ status: 403, title: 'Forbidden' }) });
    });
    await page.goto('/focus');
    await page.getByRole('button', { name: 'Sign out' }).click();
    const session = page.getByRole('group', { name: 'Session' });
    await expect(session.getByRole('status')).toContainText('Sign-out could not be confirmed');
    await expect(session.getByRole('button', { name: 'Sign out' })).toBeVisible();
    await expect(page.getByText('No assigned work to show')).toBeVisible();
    expect(attempts).toBe(2);
  });

  const states: { name: string; path: string; session: SessionMock; title: string }[] = [
    { name: 'signed out', path: '/focus', session: { json: signedOutSession }, title: 'You are signed out' },
    { name: 'signed in', path: '/focus', session: { json: signedInSession }, title: 'No assigned work to show' },
    { name: 'sign-in failed', path: '/focus?sign-in=failed', session: { json: signedOutSession }, title: 'Sign-in was not completed' },
    { name: 'provider error', path: '/focus?sign-in=unavailable', session: { json: signedOutSession }, title: 'The identity provider is unavailable' },
    { name: 'session problem', path: '/focus', session: { status: 503 }, title: 'The session could not be checked' },
    { name: 'kept session not confirmed at start', path: '/focus', session: { status: 503, csrf: syntheticCsrf }, title: 'The session could not be checked' },
  ];
  for (const theme of ['light', 'dark'] as const) {
    for (const width of [1280, 320]) {
      for (const state of states) {
        test(`session state ${state.name} · ${theme} · ${width}px: no axe violations, no overflow, 44px targets`, async ({ page }) => {
          await page.emulateMedia({ colorScheme: theme });
          await page.setViewportSize({ width, height: 900 });
          await mockSession(page, state.session);
          await page.goto(state.path);
          await expect(page.getByText(state.title)).toBeVisible();
          expect(await scan(page)).toEqual([]);
          await expectNoHorizontalOverflow(page);
          await expectControlTargets(page);
        });
      }

      test(`session state expired · ${theme} · ${width}px: no axe violations`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        const session = await mockSession(page, { json: signedInSession });
        await page.clock.install();
        await page.goto('/focus');
        await expect(page.getByText('No assigned work to show')).toBeVisible();
        session.set({ json: signedOutSession });
        await page.clock.runFor(61_000);
        await expect(page.getByText('Your session ended')).toBeVisible();
        expect(await scan(page)).toEqual([]);
        await expectNoHorizontalOverflow(page);
      });

      test(`session state not confirmed after signed in · ${theme} · ${width}px: no axe violations, no overflow, 44px targets`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        const session = await mockSession(page, { json: signedInSession });
        await page.clock.install();
        await page.goto('/focus');
        await expect(page.getByText('No assigned work to show')).toBeVisible();
        session.set({ status: 503 });
        await page.clock.runFor(61_000);
        await expect(page.getByText('The session could not be checked')).toBeVisible();
        await expect(page.getByRole('group', { name: 'Session' }).getByRole('button', { name: 'Sign out' })).toBeVisible();
        expect(await scan(page)).toEqual([]);
        await expectNoHorizontalOverflow(page);
        await expectControlTargets(page);
      });
    }
  }
});
