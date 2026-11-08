// @vitest-environment node
import { once } from 'node:events';
import { createServer as createHttpServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';
import { createServer, type ViteDevServer } from 'vite';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

/**
 * The dev server proxies the routing contract's backend paths (`/api`, `/actuator`) and nothing else.
 * Regression: a bare `/api` prefix also matched the frontend's own `/api-compatibility.json` module, so
 * `npm run dev` forwarded it to the backend and rendered a blank page. The built bundle inlines the
 * JSON, which is why the preview-based browser suites never saw it.
 */
const frontendRoot = fileURLToPath(new URL('../..', import.meta.url));

let backend: Server;
let vite: ViteDevServer;
let viteUrl: string;
const backendPaths: string[] = [];

function baseUrl(server: Server): string {
  const { port } = server.address() as AddressInfo;
  return `http://127.0.0.1:${port}`;
}

beforeAll(async () => {
  backend = createHttpServer((request, response) => {
    backendPaths.push(request.url ?? '');
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ from: 'backend' }));
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');

  const previousBackendUrl = process.env.OWLMAST_BACKEND_URL;
  process.env.OWLMAST_BACKEND_URL = baseUrl(backend);
  try {
    vite = await createServer({
      root: frontendRoot,
      configFile: `${frontendRoot}vite.config.ts`,
      logLevel: 'silent',
      server: { host: '127.0.0.1', port: 0, strictPort: false, hmr: false, watch: null },
    });
  } finally {
    if (previousBackendUrl === undefined) delete process.env.OWLMAST_BACKEND_URL;
    else process.env.OWLMAST_BACKEND_URL = previousBackendUrl;
  }
  await vite.listen();
  const address = vite.httpServer?.address() as AddressInfo;
  viteUrl = `http://127.0.0.1:${address.port}`;
}, 30_000);

afterAll(async () => {
  await vite.close();
  backend.close();
  await once(backend, 'close');
});

describe('dev server proxy (routing contract: /api and /actuator only)', () => {
  it('serves the frontend compatibility manifest itself instead of forwarding it to the backend', async () => {
    backendPaths.length = 0;
    const response = await fetch(`${viteUrl}/api-compatibility.json?import`);
    expect(response.status).toBe(200);
    expect(await response.text()).toContain('supportedApiContract');
    expect(backendPaths).toEqual([]);
  });

  it('forwards backend API and actuator paths to the backend', async () => {
    backendPaths.length = 0;
    const api = await fetch(`${viteUrl}/api/compatibility`);
    const readiness = await fetch(`${viteUrl}/actuator/health/readiness`);
    expect(await api.json()).toEqual({ from: 'backend' });
    expect(await readiness.json()).toEqual({ from: 'backend' });
    expect(backendPaths).toEqual(['/api/compatibility', '/actuator/health/readiness']);
  });
});
