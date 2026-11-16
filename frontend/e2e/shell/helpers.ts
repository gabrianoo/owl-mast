import { expect, type Page, type Route } from '@playwright/test';

export const DESCRIPTOR_URL = '**/api/compatibility';

export const compatibleDescriptor = {
  service: 'owl-mast-backend',
  backendVersion: '0.1.0-SNAPSHOT',
  apiContract: { major: 1, minor: 1 },
};

export const SESSION_URL = '**/api/session';
export const SIGN_OUT_URL = '**/api/session/sign-out';

/** Synthetic person and CSRF token: nothing here is a real account or credential. */
export const syntheticPerson = { principalId: 'principal-synthetic-1', displayName: 'Ada Synthetic' };
export const syntheticCsrf = { headerName: 'X-CSRF-TOKEN', token: 'synthetic-csrf-token' };
export const signedInSession = { state: 'signed-in', person: syntheticPerson, csrf: syntheticCsrf };
export const signedOutSession = { state: 'signed-out' };

/**
 * `csrf` on a status: the extension member the backend adds to the 503 of the session read while
 * it keeps a session it cannot confirm.
 */
export type SessionMock = { json: unknown } | { status: number; csrf?: unknown };

/**
 * Intercepts the session read. `current` may be replaced by the test to change what later reads
 * answer. Registered after the default of ./test.ts, so it takes precedence over it.
 */
export async function mockSession(page: Page, initial: SessionMock): Promise<{ hits: () => number; set: (next: SessionMock) => void }> {
  let hits = 0;
  let current = initial;
  await page.route(SESSION_URL, (route: Route) => {
    hits += 1;
    if ('json' in current) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(current.json) });
    }
    return route.fulfill({
      status: current.status,
      contentType: 'application/problem+json',
      body: JSON.stringify({ status: current.status, title: 'mocked', ...(current.csrf === undefined ? {} : { csrf: current.csrf }) }),
    });
  });
  return {
    hits: () => hits,
    set: (next) => {
      current = next;
    },
  };
}

export type DescriptorMock = { json: unknown } | { status: number; body?: string; contentType?: string };

/** Intercepts the compatibility descriptor so every connection state can be produced without a backend. */
export async function mockDescriptor(page: Page, mock: DescriptorMock): Promise<{ hits: () => number }> {
  let hits = 0;
  await page.route(DESCRIPTOR_URL, (route: Route) => {
    hits += 1;
    if ('json' in mock) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mock.json) });
    }
    return route.fulfill({
      status: mock.status,
      contentType: mock.contentType ?? 'application/problem+json',
      body: mock.body ?? JSON.stringify({ status: mock.status, title: 'mocked' }),
    });
  });
  return { hits: () => hits };
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(widths.scroll, `page scrollWidth ${widths.scroll} exceeds viewport ${widths.client}`).toBeLessThanOrEqual(widths.client);
}

/** Every visible interactive control must offer a 44×44 CSS px hit area (DESIGN.md control-target). */
export async function expectControlTargets(page: Page, minimum = 44): Promise<void> {
  const boxes = await page.evaluate(() => {
    const selector = 'a[href], button, input, select, summary, [role="button"]';
    return [...document.querySelectorAll<HTMLElement>(selector)]
      .filter((element) => {
        const style = getComputedStyle(element);
        return style.visibility !== 'hidden' && style.display !== 'none' && element.getClientRects().length > 0;
      })
      .filter((element) => !(element instanceof HTMLInputElement && element.type === 'radio' && element.closest('label')))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return { label: (element.textContent ?? element.getAttribute('aria-label') ?? element.tagName).trim().slice(0, 40), width: rect.width, height: rect.height };
      });
  });
  expect(boxes.length).toBeGreaterThan(0);
  for (const box of boxes) {
    expect(box.height, `${box.label} height`).toBeGreaterThanOrEqual(minimum - 0.5);
    expect(box.width, `${box.label} width`).toBeGreaterThanOrEqual(minimum - 0.5);
  }
}

export function rgb(hex: string): string {
  const value = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((offset) => parseInt(value.slice(offset, offset + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
}
