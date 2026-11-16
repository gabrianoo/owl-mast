import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client.ts';
import {
  createSessionLink,
  parseKeptSession,
  parseSession,
  parseSignOut,
  readSignInResult,
  withoutSignInResult,
} from './session.ts';

function json(body: unknown, status = 200, contentType = 'application/json'): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': contentType } });
}

const person = { principalId: 'principal-1', displayName: 'Ada Synthetic' };
const csrf = { headerName: 'X-CSRF-TOKEN', token: 'abc-123_xyz' };

describe('session answer', () => {
  it('reads the two states and nothing else', () => {
    expect(parseSession({ state: 'signed-out' })).toEqual({ state: 'signed-out' });
    expect(parseSession({ state: 'signed-in', person, csrf, extra: 'ignored' })).toEqual({ state: 'signed-in', person, csrf });
    for (const body of [null, 'signed-in', [], {}, { state: 'pending' }, { state: 'signed-in' }, { state: 'signed-in', person }, { state: 'signed-in', csrf }]) {
      expect(() => parseSession(body), JSON.stringify(body)).toThrow();
    }
  });

  it('refuses a person without an id or a display name', () => {
    expect(() => parseSession({ state: 'signed-in', person: { displayName: 'Ada' }, csrf })).toThrow();
    expect(() => parseSession({ state: 'signed-in', person: { principalId: 'p', displayName: '  ' }, csrf })).toThrow();
    expect(() => parseSession({ state: 'signed-in', person: { principalId: 'p', displayName: 'x'.repeat(257) }, csrf })).toThrow();
    expect(() => parseSession({ state: 'signed-in', person: { principalId: 7, displayName: 'Ada' }, csrf })).toThrow();
  });

  it('refuses a csrf token that could not be sent as a header', () => {
    const answer = (value: unknown) => ({ state: 'signed-in', person, csrf: value });
    expect(() => parseSession(answer({ headerName: 'X CSRF', token: 't' }))).toThrow();
    expect(() => parseSession(answer({ headerName: 'X-CSRF-TOKEN:\r\nCookie', token: 't' }))).toThrow();
    expect(() => parseSession(answer({ headerName: 'X-CSRF-TOKEN', token: 'a\r\nb' }))).toThrow();
    expect(() => parseSession(answer({ headerName: 'X-CSRF-TOKEN', token: '' }))).toThrow();
    expect(() => parseSession(answer({ headerName: 'X-CSRF-TOKEN', token: 'x'.repeat(4097) }))).toThrow();
    expect(() => parseSession(answer({ headerName: 'X-CSRF-TOKEN' }))).toThrow();
  });

  it('reads the csrf token of a kept session with the same checks, and nothing from anything else', () => {
    expect(parseKeptSession(csrf)).toEqual(csrf);
    expect(parseKeptSession({ ...csrf, extra: 'ignored' })).toEqual(csrf);
    for (const value of [
      undefined,
      null,
      'X-CSRF-TOKEN',
      [],
      {},
      { headerName: 'X-CSRF-TOKEN' },
      { token: 't' },
      { headerName: 'X CSRF', token: 't' },
      { headerName: 'X-CSRF-TOKEN:\r\nCookie', token: 't' },
      { headerName: 'X-CSRF-TOKEN', token: 'a\r\nb' },
      { headerName: 'X-CSRF-TOKEN', token: '' },
      { headerName: 'X-CSRF-TOKEN', token: 'x'.repeat(4097) },
    ]) {
      expect(parseKeptSession(value), JSON.stringify(value)).toBeUndefined();
    }
  });

  it('reports the identity provider session as ended only when told so', () => {
    expect(parseSignOut({ state: 'signed-out', identityProvider: 'ended' })).toEqual({ state: 'signed-out', identityProvider: 'ended' });
    expect(parseSignOut({ state: 'signed-out', identityProvider: 'unconfirmed' }).identityProvider).toBe('unconfirmed');
    expect(parseSignOut({ state: 'signed-out' }).identityProvider).toBe('unconfirmed');
    expect(parseSignOut({ state: 'signed-out', identityProvider: 'whatever' }).identityProvider).toBe('unconfirmed');
    expect(() => parseSignOut({ state: 'signed-in' })).toThrow();
    expect(() => parseSignOut(null)).toThrow();
  });
});

describe('sign-in result in the address', () => {
  it('reads failed and unavailable; an unknown value still means the sign-in did not complete', () => {
    expect(readSignInResult('')).toBeUndefined();
    expect(readSignInResult('?other=1')).toBeUndefined();
    expect(readSignInResult('?sign-in=failed')).toBe('failed');
    expect(readSignInResult('?sign-in=unavailable')).toBe('unavailable');
    expect(readSignInResult('?sign-in=anything')).toBe('failed');
  });

  it('removes only its own parameter', () => {
    expect(withoutSignInResult('/', '?sign-in=failed', '')).toBe('/');
    expect(withoutSignInResult('/focus', '?a=1&sign-in=unavailable&b=2', '#top')).toBe('/focus?a=1&b=2#top');
  });
});

describe('session link', () => {
  it('holds the csrf token and tells every listener about a 401 until it unsubscribes', () => {
    const link = createSessionLink();
    expect(link.csrf()).toBeUndefined();
    link.setCsrf(csrf);
    expect(link.csrf()).toEqual(csrf);
    const first = vi.fn();
    const second = vi.fn();
    const stopFirst = link.onUnauthorized(first);
    link.onUnauthorized(second);
    link.unauthorized();
    stopFirst();
    link.unauthorized();
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(2);
    link.setCsrf(undefined);
    expect(link.csrf()).toBeUndefined();
  });
});

describe('unsafe calls (CSRF contract)', () => {
  it('sends the csrf header of the current session, same-origin credentials and no stored token', async () => {
    const link = createSessionLink();
    link.setCsrf(csrf);
    const fetchImpl = vi.fn<typeof fetch>(() =>
      Promise.resolve(json({ state: 'signed-out', identityProvider: 'ended' })),
    );
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => true, session: link });
    const result = await client.post('/session/sign-out', { protected: true }, parseSignOut);
    expect(result).toEqual({ kind: 'ok', value: { state: 'signed-out', identityProvider: 'ended' } });
    const [input, init] = fetchImpl.mock.calls[0] ?? [];
    expect(input).toBe('/api/session/sign-out');
    expect(init?.method).toBe('POST');
    expect(init?.credentials).toBe('same-origin');
    expect(init?.cache).toBe('no-store');
    expect(init?.body).toBeUndefined();
    const headers = init?.headers as Record<string, string>;
    expect(headers['X-CSRF-TOKEN']).toBe('abc-123_xyz');
    expect(headers.Authorization).toBeUndefined();
    expect(headers['Content-Type']).toBeUndefined();
  });

  it('sends a JSON body when one is given and no csrf header without a session', async () => {
    const fetchImpl = vi.fn<typeof fetch>(() => Promise.resolve(json({ ok: true })));
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => true, session: createSessionLink() });
    await client.post('/things', { protected: true }, (body) => body, { name: 'x' });
    const init = fetchImpl.mock.calls[0]?.[1];
    const headers = init?.headers as Record<string, string>;
    expect(init?.body).toBe('{"name":"x"}');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['X-CSRF-TOKEN']).toBeUndefined();
  });

  it('never adds the csrf header to a GET', async () => {
    const link = createSessionLink();
    link.setCsrf(csrf);
    const fetchImpl = vi.fn<typeof fetch>(() => Promise.resolve(json({ state: 'signed-out' })));
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => true, session: link });
    await client.get('/session', { protected: false }, parseSession);
    expect((fetchImpl.mock.calls[0]?.[1]?.headers as Record<string, string>)['X-CSRF-TOKEN']).toBeUndefined();
  });

  it('refuses a protected unsafe call while offline before the network is touched', async () => {
    const fetchImpl = vi.fn();
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => false });
    expect(await client.post('/session/sign-out', { protected: true }, parseSignOut)).toEqual({ kind: 'offline' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('tells the session about a 401 on a protected call, and not about a 403 or a public 401', async () => {
    const link = createSessionLink();
    const heard = vi.fn();
    link.onUnauthorized(heard);
    const statuses = [401, 403, 401];
    const fetchImpl = vi.fn(() => Promise.resolve(json({ status: statuses[0], title: 'x' }, statuses.shift(), 'application/problem+json')));
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => true, session: link });
    expect(await client.get('/protected', { protected: true }, (body) => body)).toEqual({ kind: 'denied', status: 401 });
    expect(heard).toHaveBeenCalledTimes(1);
    expect(await client.post('/protected', { protected: true }, (body) => body)).toEqual({ kind: 'denied', status: 403 });
    expect(await client.get('/public', { protected: false }, (body) => body)).toEqual({ kind: 'denied', status: 401 });
    expect(heard).toHaveBeenCalledTimes(1);
  });
});
