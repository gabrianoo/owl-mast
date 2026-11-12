import { describe, expect, it } from 'vitest';
import { readFrontendFile } from '../testing/planning.ts';
import { DESTINATIONS, HOME } from './destinations.ts';

/**
 * The image's start-up guard refuses an API prefix that names a page of the shell: nginx would
 * answer 404 at and below it, so a reload of that page would fail. The guard runs in the runtime
 * image, which has no copy of this module, so it keeps its own list; this test keeps the two equal.
 */
describe('shell destinations and the image start-up guard', () => {
  const guard = readFrontendFile('docker-entrypoint.d/16-owlmast-api-prefix.envsh');
  const routes = DESTINATIONS.filter((destination) => destination !== HOME).map((destination) => destination.path);

  it('every destination below the root is one lower-case path segment', () => {
    // The guard compares the first segment of the prefix, exactly as the router compares paths.
    for (const path of routes) expect(path).toMatch(/^\/[a-z0-9-]+$/);
    expect(new Set(routes).size).toBe(routes.length);
  });

  it('the guard refuses exactly the destinations the router serves', () => {
    const declarations = [...guard.matchAll(/^owlmast_shell_routes="([^"]*)"$/gm)];
    expect(declarations).toHaveLength(1);
    const refused = (declarations[0]?.[1] ?? '').split(' ');
    expect([...refused].sort()).toEqual(routes.map((path) => path.slice(1)).sort());
  });
});
