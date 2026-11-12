/**
 * Runtime configuration handed to the shell by its own image (nginx template) as
 * `/owlmast-config.json`. The only value today is the routing contract's API path prefix
 * (chart value `routing.apiPathPrefix`, env `OWLMAST_API_PATH_PREFIX`). Development servers proxy
 * `/api`, so the default applies when the file is absent.
 */
export interface RuntimeConfig {
  apiPathPrefix: string;
}

export const DEFAULT_RUNTIME_CONFIG: RuntimeConfig = { apiPathPrefix: '/api' };
export const RUNTIME_CONFIG_PATH = '/owlmast-config.json';

const PREFIX_PATTERN = /^\/[A-Za-z0-9._~\-/]*$/;

/**
 * An absolute path of unreserved characters with at least one segment, no empty segment (`//host`
 * would be read as another origin) and no `.` or `..` segment; one trailing slash is tolerated. The
 * root is refused: the shell itself is served there, so `/compatibility` would answer with the
 * shell. The image's start-up guard (docker-entrypoint.d/16-owlmast-api-prefix.envsh) applies the
 * same rule and additionally refuses the paths the image serves itself; both are a subset of what
 * the chart's `owl-mast.validatePathPrefix` accepts. Anything else falls back to the default.
 */
function isSafePrefix(value: string): boolean {
  if (!PREFIX_PATTERN.test(value)) return false;
  if (value === '/') return false;
  const path = value.endsWith('/') ? value.slice(0, -1) : value;
  return path
    .split('/')
    .slice(1)
    .every((segment) => segment !== '' && segment !== '.' && segment !== '..');
}

export function normalizeApiPathPrefix(value: unknown): string {
  if (typeof value !== 'string' || !isSafePrefix(value)) {
    return DEFAULT_RUNTIME_CONFIG.apiPathPrefix;
  }
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

export async function loadRuntimeConfig(fetchImpl: typeof fetch = fetch): Promise<RuntimeConfig> {
  try {
    const response = await fetchImpl(RUNTIME_CONFIG_PATH, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!response.ok) {
      return DEFAULT_RUNTIME_CONFIG;
    }
    const body: unknown = await response.json();
    const prefix = typeof body === 'object' && body !== null ? (body as Record<string, unknown>).apiPathPrefix : undefined;
    return { apiPathPrefix: normalizeApiPathPrefix(prefix) };
  } catch {
    return DEFAULT_RUNTIME_CONFIG;
  }
}
