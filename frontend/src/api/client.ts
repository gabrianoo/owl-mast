import type { SessionLink } from './session.ts';
import { PROBLEM_MEDIA_TYPE, parseProblem, type ProblemDetail } from './problem.ts';

/**
 * Backend client with the state vocabulary the shell renders (UX-DR26/42). Protected requests
 * (`protected: true`) are refused while offline before any network or cache access, so offline never
 * discloses protected content from a cache. Public requests (`protected: false`) are still attempted:
 * `navigator.onLine` is advisory and a public answer discloses nothing. Every request uses
 * `cache: 'no-store'`. 401/403 become `denied`, 404 `not-found`, everything else `error`. Bodies are
 * parsed as JSON only. Of an error body only the status and the title are carried on, plus the one
 * member a request names with `errorExtension`, unparsed: the caller checks it before use.
 *
 * Session (OM-02.01): the only credential is the HttpOnly session cookie, sent to the same origin
 * (`credentials: 'same-origin'`); no token is ever held by this client. Unsafe methods (`post`) send
 * the CSRF header the session answer supplied. A 401 on a protected call means the session is gone:
 * the session link is told, so the shell re-reads the session and removes protected content. A 403
 * is a denial for a signed-in person and says nothing about the session.
 */
export type ApiResult<T> =
  | { kind: 'ok'; value: T }
  | { kind: 'offline' }
  | { kind: 'denied'; status: 401 | 403 }
  | { kind: 'not-found' }
  | { kind: 'error'; status?: number; problem?: ProblemDetail; extension?: unknown };

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
  /** Supplies the CSRF token for unsafe calls and hears about a 401 on a protected call. */
  session?: SessionLink;
}

export interface RequestOptions {
  /**
   * Protected content requires current authorization: `true` refuses the request while offline
   * before the network or a cache is touched. `false` marks public content, which is attempted and
   * reports `offline` or `error` when the request fails.
   */
  protected: boolean;
  signal?: AbortSignal;
  /**
   * Names one top-level member of an error body (an RFC 9457 extension member) to carry on the
   * error result as `extension`, as received. Nothing else of an error body is exposed.
   */
  errorExtension?: string;
}

export interface ApiClient {
  get<T>(path: string, options: RequestOptions, parse: (body: unknown) => T): Promise<ApiResult<T>>;
  /**
   * An unsafe call. `body` is sent as JSON when given. The CSRF header of the current session is
   * added; without a session no header is sent and the backend refuses the call (401 or 403).
   */
  post<T>(path: string, options: RequestOptions, parse: (body: unknown) => T, body?: unknown): Promise<ApiResult<T>>;
}

export function joinPath(prefix: string, path: string): string {
  const base = prefix.endsWith('/') ? prefix.slice(0, -1) : prefix;
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

/** The member `name` of an error body, when the request asked for it and the body has it as its own member. */
function extensionOf(body: unknown, name: string | undefined): unknown {
  if (name === undefined || typeof body !== 'object' || body === null || Array.isArray(body)) return undefined;
  return Object.hasOwn(body, name) ? (body as Record<string, unknown>)[name] : undefined;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const isOnline = options.isOnline ?? (() => typeof navigator === 'undefined' || navigator.onLine);

  async function send<T>(
    method: 'GET' | 'POST',
    path: string,
    request: RequestOptions,
    parse: (body: unknown) => T,
    body?: unknown,
  ): Promise<ApiResult<T>> {
    if (request.protected && !isOnline()) {
      return { kind: 'offline' };
    }
    const headers: Record<string, string> = { Accept: `application/json, ${PROBLEM_MEDIA_TYPE}` };
    if (method !== 'GET') {
      const csrf = options.session?.csrf();
      if (csrf) headers[csrf.headerName] = csrf.token;
      if (body !== undefined) headers['Content-Type'] = 'application/json';
    }
    let response: Response;
    try {
      response = await fetchImpl(joinPath(options.apiPathPrefix, path), {
        method,
        cache: 'no-store',
        credentials: 'same-origin',
        headers,
        ...(method !== 'GET' && body !== undefined ? { body: JSON.stringify(body) } : {}),
        ...(request.signal ? { signal: request.signal } : {}),
      });
    } catch {
      return isOnline() ? { kind: 'error' } : { kind: 'offline' };
    }
    if (response.status === 401 || response.status === 403) {
      if (response.status === 401 && request.protected) {
        options.session?.unauthorized();
      }
      return { kind: 'denied', status: response.status };
    }
    if (response.status === 404) {
      return { kind: 'not-found' };
    }
    if (!response.ok) {
      let problem: ProblemDetail | undefined;
      let extension: unknown;
      try {
        const errorBody: unknown = await response.json();
        problem = parseProblem(errorBody, response.status);
        extension = extensionOf(errorBody, request.errorExtension);
      } catch {
        problem = undefined;
      }
      return {
        kind: 'error',
        status: response.status,
        ...(problem === undefined ? {} : { problem }),
        ...(extension === undefined ? {} : { extension }),
      };
    }
    try {
      return { kind: 'ok', value: parse(await response.json()) };
    } catch {
      return { kind: 'error', status: response.status };
    }
  }

  return {
    get: (path, request, parse) => send('GET', path, request, parse),
    post: (path, request, parse, body) => send('POST', path, request, parse, body),
  };
}
