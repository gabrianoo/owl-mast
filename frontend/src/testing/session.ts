import type { ApiClient, ApiResult } from '../api/client.ts';
import { SESSION_PATH, SIGN_OUT_PATH, type SessionAnswer, type SignOutAnswer } from '../api/session.ts';

/** Test support: session answers and a client that serves them next to a test's own `get`. */
export const SYNTHETIC_PERSON = { principalId: 'principal-synthetic-1', displayName: 'Ada Synthetic' };
export const SYNTHETIC_CSRF = { headerName: 'X-CSRF-TOKEN', token: 'synthetic-csrf-token' };

export const signedIn: SessionAnswer = { state: 'signed-in', person: SYNTHETIC_PERSON, csrf: SYNTHETIC_CSRF };
export const signedOut: SessionAnswer = { state: 'signed-out' };

export interface SessionScript {
  /** Answer of each session read; the last one repeats. Defaults to a signed-in person. */
  session?: ApiResult<SessionAnswer>[];
  /** Answer of each sign-out call; the last one repeats. Defaults to a confirmed sign-out. */
  signOut?: ApiResult<SignOutAnswer>[];
}

export interface SessionClient extends ApiClient {
  sessionReads: () => number;
  signOutCalls: () => number;
}

function take<T>(queue: T[]): T | undefined {
  return queue.length > 1 ? queue.shift() : queue[0];
}

/**
 * Wraps a test's `get` so that the session endpoint is answered separately: the test's own answers
 * (and its call counts) stay about the endpoint it exercises.
 */
export function withSession(inner: Pick<ApiClient, 'get'>, script: SessionScript = {}): SessionClient {
  const session = script.session ?? [{ kind: 'ok', value: signedIn }];
  const signOut = script.signOut ?? [{ kind: 'ok', value: { state: 'signed-out', identityProvider: 'ended' } }];
  let sessionReads = 0;
  let signOutCalls = 0;
  return {
    get: <T,>(path: string, options: Parameters<ApiClient['get']>[1], parse: (body: unknown) => T) => {
      if (path === SESSION_PATH) {
        sessionReads += 1;
        return Promise.resolve((take(session) ?? { kind: 'error' }) as ApiResult<T>);
      }
      return inner.get(path, options, parse);
    },
    post: <T,>(path: string) => {
      if (path === SIGN_OUT_PATH) {
        signOutCalls += 1;
        return Promise.resolve((take(signOut) ?? { kind: 'error' }) as ApiResult<T>);
      }
      return Promise.resolve({ kind: 'not-found' } as ApiResult<T>);
    },
    sessionReads: () => sessionReads,
    signOutCalls: () => signOutCalls,
  };
}
