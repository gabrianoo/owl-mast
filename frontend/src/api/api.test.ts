import { describe, expect, it, vi } from 'vitest';
import { createApiClient, joinPath } from './client.ts';
import {
  SUPPORTED_CONTRACT,
  descriptorsEqual,
  evaluateCompatibility,
  formatContract,
  parseDescriptor,
} from './compatibility.ts';
import { DEFAULT_RUNTIME_CONFIG, loadRuntimeConfig, normalizeApiPathPrefix } from './config.ts';
import { parseProblem } from './problem.ts';

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  return input instanceof URL ? input.href : input.url;
}

function jsonResponse(body: unknown, status = 200, contentType = 'application/json'): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': contentType } });
}

describe('runtime config', () => {
  it('normalises the API path prefix and falls back to /api', () => {
    expect(normalizeApiPathPrefix('/api')).toBe('/api');
    expect(normalizeApiPathPrefix('/owl/api/')).toBe('/owl/api');
    expect(normalizeApiPathPrefix('/')).toBe('/');
    expect(normalizeApiPathPrefix('api')).toBe('/api');
    expect(normalizeApiPathPrefix('/api?x=1')).toBe('/api');
    expect(normalizeApiPathPrefix(42)).toBe('/api');
  });

  it('reads /owlmast-config.json without caching and tolerates its absence', async () => {
    const fetchImpl = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      expect(urlOf(input)).toBe('/owlmast-config.json');
      expect(init?.cache).toBe('no-store');
      return Promise.resolve(jsonResponse({ apiPathPrefix: '/backend' }));
    });
    expect(await loadRuntimeConfig(fetchImpl)).toEqual({ apiPathPrefix: '/backend' });
    expect(await loadRuntimeConfig(() => Promise.resolve(new Response('nope', { status: 404 })))).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(await loadRuntimeConfig(() => Promise.reject(new TypeError('network')))).toEqual(DEFAULT_RUNTIME_CONFIG);
  });
});

describe('problem details (common error envelope)', () => {
  it('keeps only status, a bounded title and type; never the detail', () => {
    const parsed = parseProblem({ status: 503, title: 'Service Unavailable', detail: 'jdbc://user:secret@host', type: 'about:blank' }, 500);
    expect(parsed).toEqual({ status: 503, title: 'Service Unavailable', type: 'about:blank' });
    expect(JSON.stringify(parsed)).not.toContain('secret');
    expect(parseProblem('garbage', 502)).toEqual({ status: 502, title: 'Request failed' });
  });
});

describe('api client (UX-DR26/42)', () => {
  const descriptor = { service: 'owl-mast-backend', backendVersion: '0.1.0', apiContract: { major: 1, minor: 0 } };

  it('joins the prefix and path', () => {
    expect(joinPath('/api', '/compatibility')).toBe('/api/compatibility');
    expect(joinPath('/api/', 'compatibility')).toBe('/api/compatibility');
    expect(joinPath('/', '/x')).toBe('/x');
  });

  it('refuses every request while offline before touching the network or a cache', async () => {
    const fetchImpl = vi.fn();
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => false });
    expect(await client.get('/compatibility', { protected: true }, parseDescriptor)).toEqual({ kind: 'offline' });
    expect(await client.get('/compatibility', { protected: false }, parseDescriptor)).toEqual({ kind: 'offline' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('requests JSON with no-store and same-origin credentials, and parses a good answer', async () => {
    const fetchImpl = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      expect(urlOf(input)).toBe('/api/compatibility');
      expect(init?.cache).toBe('no-store');
      expect(init?.credentials).toBe('same-origin');
      expect(new Headers(init?.headers).get('accept')).toContain('application/problem+json');
      return Promise.resolve(jsonResponse(descriptor));
    });
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => true });
    expect(await client.get('/compatibility', { protected: false }, parseDescriptor)).toEqual({ kind: 'ok', value: descriptor });
  });

  it('maps 401/403 to denied, 404 to not-found, other failures to error with safe problem fields', async () => {
    const responses = [
      jsonResponse({ title: 'Forbidden', status: 403 }, 403, 'application/problem+json'),
      new Response('', { status: 401 }),
      new Response('', { status: 404 }),
      jsonResponse({ title: 'Service Unavailable', status: 503, detail: 'pool exhausted at 10.0.0.1' }, 503, 'application/problem+json'),
      new Response('<html>', { status: 500 }),
    ];
    const fetchImpl = vi.fn(() => Promise.resolve(responses.shift() ?? new Response('', { status: 599 })));
    const client = createApiClient({ apiPathPrefix: '/api', fetchImpl, isOnline: () => true });
    const get = () => client.get('/x', { protected: true }, parseDescriptor);
    expect(await get()).toEqual({ kind: 'denied', status: 403 });
    expect(await get()).toEqual({ kind: 'denied', status: 401 });
    expect(await get()).toEqual({ kind: 'not-found' });
    const error = await get();
    expect(error).toEqual({ kind: 'error', status: 503, problem: { status: 503, title: 'Service Unavailable' } });
    expect(JSON.stringify(error)).not.toContain('10.0.0.1');
    expect(await get()).toEqual({ kind: 'error', status: 500 });
  });

  it('treats a network failure as error while online and as offline when the browser went offline', async () => {
    let online = true;
    const client = createApiClient({
      apiPathPrefix: '/api',
      fetchImpl: () => {
        online = false;
        return Promise.reject(new TypeError('Failed to fetch'));
      },
      isOnline: () => online,
    });
    expect(await client.get('/x', { protected: false }, parseDescriptor)).toEqual({ kind: 'offline' });
    online = true;
    const stillOnline = createApiClient({ apiPathPrefix: '/api', fetchImpl: () => Promise.reject(new TypeError('x')), isOnline: () => true });
    expect(await stillOnline.get('/x', { protected: false }, parseDescriptor)).toEqual({ kind: 'error' });
  });

  it('rejects a malformed descriptor as an error rather than rendering it', async () => {
    const client = createApiClient({
      apiPathPrefix: '/api',
      fetchImpl: () => Promise.resolve(jsonResponse({ service: 'x', apiContract: { major: '1' } })),
      isOnline: () => true,
    });
    expect(await client.get('/compatibility', { protected: false }, parseDescriptor)).toEqual({ kind: 'error', status: 200 });
  });
});

describe('compatibility policy (AC4)', () => {
  it('declares a 1.x contract with a non-negative minimum minor in the manifest', () => {
    expect(SUPPORTED_CONTRACT.major).toBe(1);
    expect(SUPPORTED_CONTRACT.minMinor).toBeGreaterThanOrEqual(0);
  });

  it('accepts equal majors with a backend minor at or above the minimum', () => {
    expect(evaluateCompatibility({ major: 1, minor: 0 }, { major: 1, minMinor: 0 }).verdict).toBe('compatible');
    expect(evaluateCompatibility({ major: 1, minor: 4 }, { major: 1, minMinor: 2 }).verdict).toBe('compatible');
  });

  it('rejects a different major or a lower minor with a reason naming both contracts', () => {
    const major = evaluateCompatibility({ major: 2, minor: 0 }, { major: 1, minMinor: 0 });
    expect(major.verdict).toBe('incompatible');
    if (major.verdict === 'incompatible') expect(major.reason).toMatch(/1\.x.*2\.0/);
    const minor = evaluateCompatibility({ major: 1, minor: 1 }, { major: 1, minMinor: 2 });
    expect(minor.verdict).toBe('incompatible');
    if (minor.verdict === 'incompatible') expect(minor.reason).toMatch(/1\.2.*1\.1/);
  });

  it('parses only well-formed descriptors', () => {
    expect(parseDescriptor({ service: 's', backendVersion: 'v', apiContract: { major: 1, minor: 2 } })).toEqual({
      service: 's',
      backendVersion: 'v',
      apiContract: { major: 1, minor: 2 },
    });
    expect(() => parseDescriptor(null)).toThrow();
    expect(() => parseDescriptor({ service: 's', backendVersion: 'v' })).toThrow();
    expect(() => parseDescriptor({ service: 's', backendVersion: 'v', apiContract: { major: -1, minor: 0 } })).toThrow();
    expect(() => parseDescriptor({ service: 's', backendVersion: 'v', apiContract: { major: 1.5, minor: 0 } })).toThrow();
    expect(formatContract({ major: 1, minor: 3 })).toBe('1.3');
    const a = { service: 's', backendVersion: 'v', apiContract: { major: 1, minor: 0 } };
    expect(descriptorsEqual(a, { ...a })).toBe(true);
    expect(descriptorsEqual(a, { ...a, backendVersion: 'w' })).toBe(false);
  });
});
