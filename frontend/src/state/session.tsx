import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useApi } from '../api/ApiProvider.tsx';
import { joinPath } from '../api/client.ts';
import {
  SESSION_PATH,
  SIGN_IN_PATH,
  SIGN_OUT_PATH,
  parseSession,
  parseSignOut,
  readSignInResult,
  withoutSignInResult,
  type SessionLink,
  type SessionPerson,
  type SignInResult,
} from '../api/session.ts';

/**
 * Session state of the shell (OM-02.01). Every kind is rendered distinctly, and only `signed-in`
 * shows content that needs authorization:
 *
 * - `loading`: the first read is in flight. It is bounded ({@link SESSION_READ_TIMEOUT_MS}); an
 *   unanswered read becomes `problem`, never a permanent pending state.
 * - `signed-out`: nobody is signed in. `identityProvider: 'unconfirmed'` after a sign-out whose end
 *   at the identity provider could not be confirmed.
 * - `signed-in`: the backend named the person.
 * - `expired`: somebody was signed in and the backend no longer says so (expiry, revocation, a
 *   sign-out elsewhere, a backend restart). Protected content is removed.
 * - `sign-in-failed`: the backend returned the browser without a session (refused or not completed).
 * - `provider-error`: the identity provider could not be reached for sign-in.
 * - `problem`: the session endpoint itself did not give a usable answer. Fail closed: a read that
 *   fails while somebody is signed in also lands here, because the shell can no longer show that the
 *   session is current. `afterSignedIn` remembers that somebody was signed in, so that a later read
 *   saying nobody is reads as `expired` and not as a plain `signed-out`, and so that sign-out stays
 *   offered: the backend serves it while it cannot confirm the session (an identity provider
 *   outage), and a person on a shared device must be able to end the session then.
 *
 * The CSRF token of the last signed-in answer is kept until the backend says nobody is signed in or
 * a sign-out ended the session. A read that fails says nothing about the session, so it does not
 * take the token away: the sign-out offered in the `problem` state needs it.
 *
 * The session is read while the document is visible only: every read makes the backend renew the
 * session with the identity provider, so a tab nobody looks at must not keep a session alive.
 */
export type SessionState =
  | { kind: 'loading' }
  | { kind: 'signed-out'; identityProvider?: 'unconfirmed' }
  | { kind: 'signed-in'; person: SessionPerson }
  | { kind: 'expired' }
  | { kind: 'sign-in-failed' }
  | { kind: 'provider-error' }
  | { kind: 'problem'; afterSignedIn?: true };

export type SignOutOutcome = { ok: true; message: string } | { ok: false; message: string };

export interface SessionContextValue {
  state: SessionState;
  /** Leaves the shell for the identity provider's sign-in page (a full-page navigation). */
  signIn: () => void;
  /** Ends the session. Resolves with what actually happened; the state changes on success. */
  signOut: () => Promise<SignOutOutcome>;
  /** Reads the session again (the Retry of the problem state). */
  refresh: () => void;
}

export const SESSION_POLL_MS = 60_000;
export const SESSION_READ_TIMEOUT_MS = 10_000;

const SIGNED_OUT_MESSAGE = 'You are signed out.';
const SIGN_OUT_FAILED_MESSAGE = 'Sign-out could not be confirmed. You may still be signed in; try again.';
const SIGN_OUT_OFFLINE_MESSAGE = 'You are offline, so sign-out was not sent. You are still signed in on this browser.';

const SessionContext = createContext<SessionContextValue | null>(null);

type Read = { kind: 'signed-in'; person: SessionPerson } | { kind: 'signed-out' } | { kind: 'failed' };

function initialNotice(result: SignInResult | undefined): SessionState | undefined {
  if (result === 'unavailable') return { kind: 'provider-error' };
  if (result === 'failed') return { kind: 'sign-in-failed' };
  return undefined;
}

/** The state after a read, given the state it was read in. Exported for tests of the transitions. */
export function nextSessionState(current: SessionState, read: Read, notice?: SessionState): SessionState {
  if (read.kind === 'signed-in') {
    return { kind: 'signed-in', person: read.person };
  }
  if (read.kind === 'signed-out') {
    if (current.kind === 'signed-in') return { kind: 'expired' };
    // Somebody was signed in before the reads started failing: their session ended meanwhile.
    if (current.kind === 'problem' && current.afterSignedIn) return { kind: 'expired' };
    if (current.kind === 'loading' || current.kind === 'problem') return notice ?? { kind: 'signed-out' };
    // Already one of the signed-out states: keep what it says (expired, failed, provider error).
    return current;
  }
  // The read failed. Nobody is shown as signed in on the strength of an answer that did not arrive.
  if (current.kind === 'signed-in') return { kind: 'problem', afterSignedIn: true };
  if (current.kind === 'loading') return { kind: 'problem' };
  return current;
}

export interface SessionProviderProps {
  apiPathPrefix: string;
  link: SessionLink;
  children: ReactNode;
  pollIntervalMs?: number;
  readTimeoutMs?: number;
  /** Test seam: replaces the full-page navigation to the sign-in endpoint. */
  navigate?: (url: string) => void;
}

export function SessionProvider({
  apiPathPrefix,
  link,
  children,
  pollIntervalMs = SESSION_POLL_MS,
  readTimeoutMs = SESSION_READ_TIMEOUT_MS,
  navigate,
}: SessionProviderProps) {
  const api = useApi();
  const [state, setState] = useState<SessionState>({ kind: 'loading' });
  const stateRef = useRef<SessionState>(state);
  const noticeRef = useRef<SessionState | undefined>(undefined);
  const noticeReadRef = useRef(false);
  const sequenceRef = useRef(0);
  const signingOutRef = useRef(false);
  const mountedRef = useRef(true);

  const apply = useCallback(
    (next: SessionState) => {
      stateRef.current = next;
      setState(next);
    },
    [],
  );

  const read = useCallback(async (): Promise<Read> => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
    }, readTimeoutMs);
    try {
      // Public: the endpoint answers for anybody and discloses nothing to a signed-out caller.
      const result = await api.get(SESSION_PATH, { protected: false, signal: controller.signal }, parseSession);
      if (result.kind !== 'ok') {
        // No answer about the session: the CSRF token of the last signed-in answer stays.
        return { kind: 'failed' };
      }
      if (result.value.state === 'signed-in') {
        link.setCsrf(result.value.csrf);
        return { kind: 'signed-in', person: result.value.person };
      }
      link.setCsrf(undefined);
      return { kind: 'signed-out' };
    } catch {
      return { kind: 'failed' };
    } finally {
      clearTimeout(timer);
    }
  }, [api, link, readTimeoutMs]);

  const refresh = useCallback(() => {
    const sequence = ++sequenceRef.current;
    void read().then((answer) => {
      // Only the newest read decides, and a sign-out in flight decides for itself.
      if (!mountedRef.current || sequence !== sequenceRef.current || signingOutRef.current) return;
      apply(nextSessionState(stateRef.current, answer, noticeRef.current));
      // The result of a sign-in belongs to the first answer after it. Once an answer was applied
      // it is spent: a later, unrelated signed-out read must not bring it back.
      if (answer.kind !== 'failed') noticeRef.current = undefined;
    });
  }, [apply, read]);

  useEffect(() => {
    mountedRef.current = true;
    if (!noticeReadRef.current) {
      // Read once, then removed from the address, so a reload or a copied link does not repeat it.
      noticeReadRef.current = true;
      const result = readSignInResult(window.location.search);
      noticeRef.current = initialNotice(result);
      if (result !== undefined) {
        window.history.replaceState(
          window.history.state,
          '',
          withoutSignInResult(window.location.pathname, window.location.search, window.location.hash),
        );
      }
    }
    refresh();
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    // A hidden tab does not poll: each read renews the session, and an unattended tab would keep
    // it from ever idling out. Becoming visible reads at once (below).
    const interval = setInterval(onVisible, pollIntervalMs);
    window.addEventListener('focus', refresh);
    // A read that failed while offline is repeated as soon as the browser reports a connection.
    window.addEventListener('online', refresh);
    document.addEventListener('visibilitychange', onVisible);
    const stopListening = link.onUnauthorized(refresh);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('online', refresh);
      document.removeEventListener('visibilitychange', onVisible);
      stopListening();
    };
  }, [link, pollIntervalMs, refresh]);

  const signIn = useCallback(() => {
    const url = joinPath(apiPathPrefix, SIGN_IN_PATH);
    if (navigate) {
      navigate(url);
    } else {
      window.location.assign(url);
    }
  }, [apiPathPrefix, navigate]);

  const signOut = useCallback(async (): Promise<SignOutOutcome> => {
    signingOutRef.current = true;
    try {
      let result = await api.post(SIGN_OUT_PATH, { protected: true }, parseSignOut);
      if (result.kind === 'denied' && result.status === 403) {
        // The CSRF token was missing or stale: read the session once and try once more.
        const answer = await read();
        if (answer.kind === 'signed-in') {
          result = await api.post(SIGN_OUT_PATH, { protected: true }, parseSignOut);
        } else if (answer.kind === 'signed-out') {
          result = { kind: 'denied', status: 401 };
        }
      }
      if (!mountedRef.current) {
        return { ok: true, message: SIGNED_OUT_MESSAGE };
      }
      if (result.kind === 'ok') {
        sequenceRef.current += 1;
        link.setCsrf(undefined);
        apply(result.value.identityProvider === 'ended' ? { kind: 'signed-out' } : { kind: 'signed-out', identityProvider: 'unconfirmed' });
        return { ok: true, message: SIGNED_OUT_MESSAGE };
      }
      if (result.kind === 'denied' && result.status === 401) {
        // There was no session left to end.
        sequenceRef.current += 1;
        link.setCsrf(undefined);
        apply({ kind: 'signed-out' });
        return { ok: true, message: SIGNED_OUT_MESSAGE };
      }
      return { ok: false, message: result.kind === 'offline' ? SIGN_OUT_OFFLINE_MESSAGE : SIGN_OUT_FAILED_MESSAGE };
    } finally {
      signingOutRef.current = false;
    }
  }, [api, apply, link, read]);

  const value = useMemo<SessionContextValue>(() => ({ state, signIn, signOut, refresh }), [state, signIn, signOut, refresh]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error('useSession requires SessionProvider');
  }
  return value;
}
