import { PROBLEM_MEDIA_TYPE, parseProblem, type ProblemDetail } from './problem.ts';

/**
 * Backend client with the state vocabulary the shell renders (UX-DR26/42). Protected requests
 * (`protected: true`) are refused while offline before any network or cache access, so offline never
 * discloses protected content from a cache. Public requests (`protected: false`) are still attempted:
 * `navigator.onLine` is advisory and a public answer discloses nothing. Every request uses
 * `cache: 'no-store'`. 401/403 become `denied`, 404 `not-found`, everything else `error`. Bodies are
 * parsed as JSON only.
 */
export type ApiResult<T> =
  | { kind: 'ok'; value: T }
  | { kind: 'offline' }
  | { kind: 'denied'; status: 401 | 403 }
  | { kind: 'not-found' }
  | { kind: 'error'; status?: number; problem?: ProblemDetail };

export class ApiResultError extends Error {
  constructor(readonly result: Exclude<ApiResult<never>, { kind: 'ok' }>) {
    super(`api ${result.kind}`);
    this.name = 'ApiResultError';
  }
}

export interface ApiClientOptions {
  apiPathPrefix: string;
  fetchImpl?: typeof fetch;
  isOnline?: () => boolean;
}

export interface RequestOptions {
  /**
   * Protected content requires current authorization: `true` refuses the request while offline
   * before the network or a cache is touched. `false` marks public content, which is attempted and
   * reports `offline` or `error` when the request fails.
   */
  protected: boolean;
  signal?: AbortSignal;
}

export interface ApiClient {
  get<T>(path: string, options: RequestOptions, parse: (body: unknown) => T): Promise<ApiResult<T>>;
}

export function joinPath(prefix: string, path: string): string {
  const base = prefix.endsWith('/') ? prefix.slice(0, -1) : prefix;
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const isOnline = options.isOnline ?? (() => typeof navigator === 'undefined' || navigator.onLine);
  return {
    async get(path, request, parse) {
      if (request.protected && !isOnline()) {
        return { kind: 'offline' };
      }
      let response: Response;
      try {
        response = await fetchImpl(joinPath(options.apiPathPrefix, path), {
          method: 'GET',
          cache: 'no-store',
          credentials: 'same-origin',
          headers: { Accept: `application/json, ${PROBLEM_MEDIA_TYPE}` },
          ...(request.signal ? { signal: request.signal } : {}),
        });
      } catch {
        return isOnline() ? { kind: 'error' } : { kind: 'offline' };
      }
      if (response.status === 401 || response.status === 403) {
        return { kind: 'denied', status: response.status };
      }
      if (response.status === 404) {
        return { kind: 'not-found' };
      }
      if (!response.ok) {
        let problem: ProblemDetail | undefined;
        try {
          problem = parseProblem(await response.json(), response.status);
        } catch {
          problem = undefined;
        }
        return problem === undefined ? { kind: 'error', status: response.status } : { kind: 'error', status: response.status, problem };
      }
      try {
        return { kind: 'ok', value: parse(await response.json()) };
      } catch {
        return { kind: 'error', status: response.status };
      }
    },
  };
}
