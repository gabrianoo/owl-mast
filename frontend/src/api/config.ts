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

export function normalizeApiPathPrefix(value: unknown): string {
  if (typeof value !== 'string' || !PREFIX_PATTERN.test(value)) {
    return DEFAULT_RUNTIME_CONFIG.apiPathPrefix;
  }
  const trimmed = value.length > 1 ? value.replace(/\/+$/, '') : value;
  return trimmed === '' ? '/' : trimmed;
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
