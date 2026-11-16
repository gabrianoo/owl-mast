import { expect, test, type Page } from '@playwright/test';

/**
 * OM-02.01-T4 browser sign-in across the separately packaged frontend and backend, with the pinned
 * Keycloak and a synthetic realm (`./gradlew :backend:bootTestRun`). No mocks: the shell is served by
 * its own preview server, `/api` is proxied to the backend as the ingress/gateway does, and the
 * login page is Keycloak's own, on its own origin.
 *
 * The user is synthetic (`ada.synthetic`, "Ada Synthetic"). Her password is generated per run by
 * playwright.smoke.config.ts and reaches this file through the environment only.
 */
const USERNAME = 'ada.synthetic';
const DISPLAY_NAME = 'Ada Synthetic';
const APPLICATION_ORIGIN = 'http://127.0.0.1:4174';

function fixturePassword(): string {
  const password = process.env.OWLMAST_FIXTURE_USER_PASSWORD;
  if (!password) {
    throw new Error('OWLMAST_FIXTURE_USER_PASSWORD is not set: run this suite through playwright.smoke.config.ts');
  }
  return password;
}

interface SessionBody {
  state: string;
  person?: { principalId: string; displayName: string };
  csrf?: { headerName: string; token: string };
}

async function readSession(page: Page): Promise<SessionBody> {
  const response = await page.request.get('/api/session');
  expect(response.status()).toBe(200);
  return (await response.json()) as SessionBody;
}

async function signInAtKeycloak(page: Page): Promise<void> {
  await page.getByRole('main').getByRole('button', { name: 'Sign in' }).click();
  // The login form belongs to Keycloak and is served from Keycloak's origin, not from the shell's.
  await page.locator('#username').waitFor();
  expect(new URL(page.url()).origin).not.toBe(APPLICATION_ORIGIN);
  await page.locator('#username').fill(USERNAME);
  await page.locator('#password').fill(fixturePassword());
  await page.locator('#kc-login').click();
  await page.waitForURL(`${APPLICATION_ORIGIN}/`);
}

test.describe('browser sign-in with a real Keycloak (OM-02.01)', () => {
  test('signed out → Keycloak login → signed in → reload → sign out', async ({ page, context }) => {
    expect((await readSession(page)).state).toBe('signed-out');

    await page.goto('/');
    const main = page.getByRole('main');
    const session = page.getByRole('group', { name: 'Session' });
    await expect(main.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    // The public descriptor stays reachable without a session.
    await expect(page.getByText('Compatible frontend and backend')).toBeVisible();

    await signInAtKeycloak(page);
    await expect(session.getByText(`Signed in as ${DISPLAY_NAME}`)).toBeVisible();
    await expect(main.getByText('You are signed out')).toHaveCount(0);
    expect(new URL(page.url()).search).toBe('');

    // One credential in the browser: an HttpOnly session cookie for the application origin. No token
    // in a cookie a script can read, in storage or in the address.
    const cookies = await context.cookies(`${APPLICATION_ORIGIN}/api/session`);
    expect(cookies.length).toBe(1);
    expect(cookies[0]?.httpOnly).toBe(true);
    expect(cookies[0]?.secure).toBe(true);
    expect(cookies[0]?.sameSite).toBe('Lax');
    expect(await page.evaluate(() => ({ cookie: document.cookie, local: window.localStorage.length, session: window.sessionStorage.length }))).toEqual({
      cookie: '',
      local: 0,
      session: 0,
    });

    const signedIn = await readSession(page);
    expect(signedIn.state).toBe('signed-in');
    expect(signedIn.person?.displayName).toBe(DISPLAY_NAME);
    expect(signedIn.person?.principalId).toBeTruthy();
    // The principal is not the display name, the username or anything derived from them.
    expect(signedIn.person?.principalId).not.toContain('ada');
    expect(JSON.stringify(signedIn)).not.toMatch(/access_token|refresh_token|id_token|eyJ/);

    await page.reload();
    await expect(session.getByText(`Signed in as ${DISPLAY_NAME}`)).toBeVisible();
    expect((await readSession(page)).person?.principalId).toBe(signedIn.person?.principalId);

    // With a session an unknown API path is 404 problem details again.
    const missing = await page.request.get('/api/does-not-exist');
    expect(missing.status()).toBe(404);
    expect(missing.headers()['content-type']).toContain('application/problem+json');

    await session.getByRole('button', { name: 'Sign out' }).click();
    await expect(main.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
    await expect(session.getByRole('button', { name: 'Sign in' })).toBeVisible();
    // Signed out at Keycloak too: the shell does not report an unconfirmed provider session.
    await expect(main.getByText(/could not confirm that the identity provider/)).toHaveCount(0);
    expect((await readSession(page)).state).toBe('signed-out');

    await page.reload();
    await expect(main.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();
  });

  test('the same person signing in again is the same principal, and Keycloak asks for the password again after sign-out', async ({ page }) => {
    await page.goto('/');
    await signInAtKeycloak(page);
    const first = await readSession(page);
    expect(first.state).toBe('signed-in');
    await page.getByRole('group', { name: 'Session' }).getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('main').getByRole('heading', { level: 2, name: 'You are signed out' })).toBeVisible();

    // signInAtKeycloak waits for the login form: had the Keycloak session survived the sign-out, the
    // browser would have come straight back signed in and the form would never appear.
    await signInAtKeycloak(page);
    const second = await readSession(page);
    expect(second.state).toBe('signed-in');
    expect(second.person?.principalId).toBe(first.person?.principalId);
  });

  test('an unsafe call without the CSRF token is refused and leaves the session in place', async ({ page }) => {
    await page.goto('/');
    await signInAtKeycloak(page);
    const refused = await page.request.post('/api/session/sign-out');
    expect(refused.status()).toBe(403);
    expect(refused.headers()['content-type']).toContain('application/problem+json');
    expect((await readSession(page)).state).toBe('signed-in');
  });
});
