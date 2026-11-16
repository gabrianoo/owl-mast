/**
 * Browser session contract (OM-02.01, docs/identity.md). The backend holds the session and the
 * tokens; the browser holds one HttpOnly cookie that scripts cannot read. The shell learns who is
 * signed in from `GET {apiPathPrefix}/session`, which is public and answers 200:
 * `{"state":"signed-out"}` or the signed-in person with the CSRF token that unsafe calls must send.
 * An answer of any other shape is an error, never "signed in".
 *
 * One error answer says something about the session: 503 in the error envelope with the member
 * `csrf`. The backend keeps a session for this browser and cannot confirm it (an identity provider
 * outage). Nobody is shown as signed in on it, but the token lets the shell send the sign-out the
 * backend still serves ({@link parseKeptSession}).
 */
export interface SessionPerson {
  /** Opaque, stable id of the principal. Never shown as identity and never derived from a name. */
  principalId: string;
  /** Display only. A name is not identity: two people may share one, and it may change. */
  displayName: string;
}

export interface CsrfToken {
  headerName: string;
  token: string;
}

export type SessionAnswer = { state: 'signed-out' } | { state: 'signed-in'; person: SessionPerson; csrf: CsrfToken };

export type IdentityProviderSession = 'ended' | 'unconfirmed';

export interface SignOutAnswer {
  state: 'signed-out';
  /** `unconfirmed`: Owl Mast ended its session but could not confirm the identity provider ended its own. */
  identityProvider: IdentityProviderSession;
}

export const SESSION_PATH = '/session';
export const SIGN_IN_PATH = '/session/sign-in';
export const SIGN_OUT_PATH = '/session/sign-out';

/** Query parameter the backend adds when it returns the browser to the shell after a failed sign-in. */
export const SIGN_IN_RESULT_PARAMETER = 'sign-in';

const MAX_TEXT = 256;
const MAX_TOKEN = 4096;
/** An HTTP field name (RFC 9110 token), bounded: the value comes from the network and becomes a header. */
const HEADER_NAME = /^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$/;
/** Visible ASCII only: anything else cannot be a header value. */
const HEADER_VALUE = /^[\x21-\x7E]+$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function boundedText(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.trim() === '' || value.length > MAX_TEXT) {
    throw new Error(`session ${name} is missing or out of bounds`);
  }
  return value;
}

/** Name of the member that carries the CSRF token, in the signed-in answer and in the 503 of a kept session. */
export const CSRF_MEMBER = 'csrf';

/** The header name and token are checked before they can become a request header. */
function parseCsrf(value: unknown): CsrfToken {
  if (!isRecord(value)) {
    throw new Error('session csrf is not an object');
  }
  const { headerName, token } = value;
  if (typeof headerName !== 'string' || !HEADER_NAME.test(headerName)) {
    throw new Error('session csrf header name is not a header name');
  }
  if (typeof token !== 'string' || token.length > MAX_TOKEN || !HEADER_VALUE.test(token)) {
    throw new Error('session csrf token is not a header value');
  }
  return { headerName, token };
}

/**
 * The CSRF token of a session the backend keeps and cannot confirm: the `csrf` member of the 503
 * that answers the session read then. `undefined` when the member is absent or is not a usable
 * token, which leaves the failed read saying nothing about the session.
 */
export function parseKeptSession(extension: unknown): CsrfToken | undefined {
  try {
    return parseCsrf(extension);
  } catch {
    return undefined;
  }
}

export function parseSession(body: unknown): SessionAnswer {
  if (!isRecord(body)) {
    throw new Error('session answer is not an object');
  }
  if (body.state === 'signed-out') {
    return { state: 'signed-out' };
  }
  if (body.state !== 'signed-in' || !isRecord(body.person) || !isRecord(body.csrf)) {
    throw new Error('session answer has an unknown shape');
  }
  const csrf = parseCsrf(body.csrf);
  return {
    state: 'signed-in',
    person: {
      principalId: boundedText(body.person.principalId, 'principal id'),
      displayName: boundedText(body.person.displayName, 'display name'),
    },
    csrf,
  };
}

export function parseSignOut(body: unknown): SignOutAnswer {
  if (!isRecord(body) || body.state !== 'signed-out') {
    throw new Error('sign-out answer has an unknown shape');
  }
  // Anything but an explicit "ended" is reported as unconfirmed: the shell never claims more than it was told.
  return { state: 'signed-out', identityProvider: body.identityProvider === 'ended' ? 'ended' : 'unconfirmed' };
}

export type SignInResult = 'failed' | 'unavailable';

/** What the backend reported about a sign-in that did not complete, or `undefined` when it said nothing. */
export function readSignInResult(search: string): SignInResult | undefined {
  const value = new URLSearchParams(search).get(SIGN_IN_RESULT_PARAMETER);
  if (value === null) return undefined;
  // An unknown value still means "the backend sent the browser back without a session".
  return value === 'unavailable' ? 'unavailable' : 'failed';
}

/** The same location without the sign-in result, so a reload or a shared link does not repeat it. */
export function withoutSignInResult(pathname: string, search: string, hash: string): string {
  const parameters = new URLSearchParams(search);
  parameters.delete(SIGN_IN_RESULT_PARAMETER);
  const rest = parameters.toString();
  return `${pathname}${rest ? `?${rest}` : ''}${hash}`;
}

/**
 * What the API client needs from the session without depending on React: the CSRF token for unsafe
 * calls, and a way to say that a protected call was answered 401 (the session is gone).
 */
export interface SessionLink {
  csrf(): CsrfToken | undefined;
  setCsrf(token: CsrfToken | undefined): void;
  unauthorized(): void;
  onUnauthorized(listener: () => void): () => void;
}

export function createSessionLink(): SessionLink {
  let current: CsrfToken | undefined;
  const listeners = new Set<() => void>();
  return {
    csrf: () => current,
    setCsrf: (token) => {
      current = token;
    },
    unauthorized: () => {
      for (const listener of [...listeners]) listener();
    },
    onUnauthorized: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
