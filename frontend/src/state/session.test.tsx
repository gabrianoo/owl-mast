import { act, cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiClient, ApiResult } from '../api/client.ts';
import { ApiProvider, useApi } from '../api/ApiProvider.tsx';
import { createSessionLink, type SessionAnswer } from '../api/session.ts';
import { App } from '../app/App.tsx';
import { readRepositoryFile } from '../testing/planning.ts';
import { SYNTHETIC_CSRF, SYNTHETIC_PERSON, signedIn, signedOut, withSession, type SessionScript } from '../testing/session.ts';
import { SessionControl } from '../app/shell/SessionControl.tsx';
import { SESSION_READ_TIMEOUT_MS, SessionProvider, nextSessionState, useSession, type SessionState } from './session.tsx';

const descriptorGet: Pick<ApiClient, 'get'> = {
  get: <T,>() => Promise.resolve({ kind: 'not-found' } as ApiResult<T>),
};

const ok = (value: SessionAnswer): ApiResult<SessionAnswer> => ({ kind: 'ok', value });

function renderApp(script: SessionScript, path = '/focus', extra: { navigate?: (url: string) => void; sessionPollIntervalMs?: number } = {}) {
  window.history.replaceState(null, '', path);
  const client = withSession(descriptorGet, script);
  const view = render(<App config={{ apiPathPrefix: '/api' }} client={client} {...extra} />);
  return { client, view };
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

afterEach(() => {
  vi.useRealTimers();
});

const BACKEND_WEB = 'backend/src/main/java/com/aisquad/owlmast/access/adapter/web';

/**
 * The time the backend gives the identity provider to answer a renewal, read from the backend's
 * source: `CredentialValidation.PROVIDER_TIMEOUT`, which `SessionKeeper` applies to the renewal.
 */
function backendProviderTimeoutMs(): number {
  const declared = /Duration PROVIDER_TIMEOUT = Duration\.ofSeconds\((\d+)\);/.exec(
    readRepositoryFile(`${BACKEND_WEB}/CredentialValidation.java`),
  );
  if (!declared?.[1]) throw new Error('"Duration PROVIDER_TIMEOUT = Duration.ofSeconds(N);" was not found in CredentialValidation.java: adjust this reader to how the value is declared now');
  if (!readRepositoryFile(`${BACKEND_WEB}/SessionKeeper.java`).includes('.timeout(CredentialValidation.PROVIDER_TIMEOUT)')) {
    throw new Error('".timeout(CredentialValidation.PROVIDER_TIMEOUT)" was not found in SessionKeeper.java: check which value bounds the renewal now and adjust this reader');
  }
  return Number(declared[1]) * 1000;
}

describe('session transitions', () => {
  const person = SYNTHETIC_PERSON;
  const signedInState: SessionState = { kind: 'signed-in', person };

  it('a signed-in answer always wins', () => {
    for (const current of [{ kind: 'loading' }, { kind: 'expired' }, { kind: 'problem' }, { kind: 'sign-in-failed' }] as SessionState[]) {
      expect(nextSessionState(current, { kind: 'signed-in', person })).toEqual(signedInState);
    }
  });

  it('a signed-out answer ends a signed-in session as expired and keeps what a signed-out state says', () => {
    expect(nextSessionState(signedInState, { kind: 'signed-out' })).toEqual({ kind: 'expired' });
    expect(nextSessionState({ kind: 'loading' }, { kind: 'signed-out' })).toEqual({ kind: 'signed-out' });
    expect(nextSessionState({ kind: 'loading' }, { kind: 'signed-out' }, { kind: 'provider-error' })).toEqual({ kind: 'provider-error' });
    expect(nextSessionState({ kind: 'problem' }, { kind: 'signed-out' })).toEqual({ kind: 'signed-out' });
    expect(nextSessionState({ kind: 'problem' }, { kind: 'signed-out' }, { kind: 'sign-in-failed' })).toEqual({ kind: 'sign-in-failed' });
    expect(nextSessionState({ kind: 'expired' }, { kind: 'signed-out' })).toEqual({ kind: 'expired' });
    expect(nextSessionState({ kind: 'sign-in-failed' }, { kind: 'signed-out' })).toEqual({ kind: 'sign-in-failed' });
  });

  it('a failed read never leaves anybody signed in', () => {
    expect(nextSessionState(signedInState, { kind: 'failed' })).toEqual({ kind: 'problem', afterSignedIn: true });
    expect(nextSessionState({ kind: 'loading' }, { kind: 'failed' })).toEqual({ kind: 'problem' });
    expect(nextSessionState({ kind: 'problem' }, { kind: 'failed' })).toEqual({ kind: 'problem' });
    expect(nextSessionState({ kind: 'signed-out' }, { kind: 'failed' })).toEqual({ kind: 'signed-out' });
    expect(nextSessionState({ kind: 'expired' }, { kind: 'failed' })).toEqual({ kind: 'expired' });
  });
});

describe('a failed read that says a session is kept (503 with the csrf token)', () => {
  const kept = { kind: 'failed', sessionKept: true } as const;

  it('offers sign-out from every state, and names nobody', () => {
    const states: SessionState[] = [
      { kind: 'loading' },
      { kind: 'problem' },
      { kind: 'problem', afterSignedIn: true },
      { kind: 'signed-in', person: SYNTHETIC_PERSON },
      { kind: 'signed-out' },
      { kind: 'signed-out', identityProvider: 'unconfirmed' },
      { kind: 'expired' },
      { kind: 'sign-in-failed' },
      { kind: 'provider-error' },
    ];
    for (const current of states) {
      expect(nextSessionState(current, kept), current.kind).toEqual({ kind: 'problem', afterSignedIn: true });
    }
  });

  it('is followed by expired when the backend then says nobody is signed in, and stays through a plain failure', () => {
    const problem = nextSessionState({ kind: 'loading' }, kept);
    expect(nextSessionState(problem, { kind: 'failed' })).toEqual({ kind: 'problem', afterSignedIn: true });
    expect(nextSessionState(problem, { kind: 'signed-out' })).toEqual({ kind: 'expired' });
  });
});

describe('a session that ended while it could not be read', () => {
  const signedInState: SessionState = { kind: 'signed-in', person: SYNTHETIC_PERSON };

  it('is remembered across the problem state and reads as expired, not as plain signed out', () => {
    const problem = nextSessionState(signedInState, { kind: 'failed' });
    const stillProblem = nextSessionState(problem, { kind: 'failed' });
    expect(stillProblem).toEqual({ kind: 'problem', afterSignedIn: true });
    expect(nextSessionState(stillProblem, { kind: 'signed-out' })).toEqual({ kind: 'expired' });
    // Not even a sign-in notice takes its place, and a good read brings the person back.
    expect(nextSessionState(stillProblem, { kind: 'signed-out' }, { kind: 'sign-in-failed' })).toEqual({ kind: 'expired' });
    expect(nextSessionState(stillProblem, { kind: 'signed-in', person: SYNTHETIC_PERSON })).toEqual(signedInState);
  });

  it('shows "Your session ended" after signed in, a failed read and a signed-out read', async () => {
    vi.useFakeTimers();
    renderApp({ session: [ok(signedIn), { kind: 'error', status: 503 }, ok(signedOut)] }, '/focus', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByRole('heading', { level: 2, name: 'Your session ended' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: 'You are signed out' })).toBeNull();
    expect(screen.queryByText('No assigned work to show')).toBeNull();
  });
});

describe('sign-out while the session cannot be confirmed (identity provider outage)', () => {
  async function signedInThenUnconfirmed(script: SessionScript) {
    vi.useFakeTimers();
    const rendered = renderApp(script, '/focus', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    vi.useRealTimers();
    return rendered;
  }

  it('offers Sign out next to "Session not confirmed", and it ends the session', async () => {
    const { client } = await signedInThenUnconfirmed({
      session: [ok(signedIn), { kind: 'error', status: 503 }],
      signOut: [{ kind: 'ok', value: { state: 'signed-out', identityProvider: 'unconfirmed' } }],
    });
    const header = screen.getByRole('group', { name: 'Session' });
    expect(header).toHaveTextContent('Session not confirmed');
    expect(header).not.toHaveTextContent('Ada Synthetic');
    expect(screen.queryByText('No assigned work to show')).toBeNull();
    await userEvent.setup().click(within(header).getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(client.signOutCalls()).toBe(1);
    expect(screen.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveTextContent('could not confirm that the identity provider ended its own');
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
  });

  it('reports a sign-out that failed and keeps offering it', async () => {
    const { client } = await signedInThenUnconfirmed({
      session: [ok(signedIn), { kind: 'error', status: 503 }],
      signOut: [{ kind: 'error', status: 503 }],
    });
    const header = screen.getByRole('group', { name: 'Session' });
    await userEvent.setup().click(within(header).getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(client.signOutCalls()).toBe(1);
    expect(header).toHaveTextContent('Sign-out could not be confirmed. You may still be signed in; try again.');
    expect(header).toHaveTextContent('Session not confirmed');
    expect(within(header).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: 'You are signed out' })).toBeNull();
  });

  it('does not offer Sign out when nobody was signed in before the reads failed', async () => {
    renderApp({ session: [{ kind: 'error', status: 503 }] });
    await settle();
    const header = screen.getByRole('group', { name: 'Session' });
    expect(header).toHaveTextContent('Session not confirmed');
    expect(within(header).queryByRole('button', { name: 'Sign out' })).toBeNull();
  });

  /** The backend's answers to a shell that starts while it keeps a session it cannot confirm. */
  function outageBackend(options: { csrfIn503: unknown; signOut: (csrf: string | null) => Response; status?: number }) {
    const status = options.status ?? 503;
    const seen = { sessionReads: 0, signOuts: [] as (string | null)[] };
    const fetchStub = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url === '/api/session') {
        seen.sessionReads += 1;
        const body = { title: 'mocked', status, instance: '/api/session', ...(options.csrfIn503 === undefined ? {} : { csrf: options.csrfIn503 }) };
        return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/problem+json' } }));
      }
      const csrf = new Headers(init?.headers).get(SYNTHETIC_CSRF.headerName);
      seen.signOuts.push(csrf);
      return Promise.resolve(options.signOut(csrf));
    });
    return { seen, fetchStub };
  }

  const signedOutUnconfirmed = () =>
    new Response(JSON.stringify({ state: 'signed-out', identityProvider: 'unconfirmed' }), { status: 200, headers: { 'content-type': 'application/json' } });

  function renderControl(link = createSessionLink()) {
    render(
      <ApiProvider config={{ apiPathPrefix: '/api' }} session={link}>
        <SessionProvider apiPathPrefix="/api" link={link}>
          <SessionControl />
        </SessionProvider>
      </ApiProvider>,
    );
    return link;
  }

  it('a shell that starts during the outage learns the CSRF token from the 503, offers Sign out and sends the header (R2-3)', async () => {
    const { seen, fetchStub } = outageBackend({ csrfIn503: SYNTHETIC_CSRF, signOut: signedOutUnconfirmed });
    vi.stubGlobal('fetch', fetchStub);
    try {
      const link = renderControl();
      await settle();
      await settle();
      const header = screen.getByRole('group', { name: 'Session' });
      expect(header).toHaveTextContent('Session not confirmed');
      expect(header).not.toHaveTextContent('Signed in');
      expect(link.csrf()).toEqual(SYNTHETIC_CSRF);
      await userEvent.setup().click(within(header).getByRole('button', { name: 'Sign out' }));
      await settle();
      await settle();
      expect(seen.signOuts).toEqual([SYNTHETIC_CSRF.token]);
      expect(header).toHaveTextContent('Signed out');
      expect(link.csrf()).toBeUndefined();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('a 503 without a usable csrf member says nothing about a session: no Sign out, no token', async () => {
    for (const csrfIn503 of [undefined, { headerName: 'X CSRF', token: 't' }, 'synthetic-csrf-token']) {
      const { fetchStub } = outageBackend({ csrfIn503, signOut: signedOutUnconfirmed });
      vi.stubGlobal('fetch', fetchStub);
      try {
        const link = renderControl();
        await settle();
        await settle();
        const header = screen.getByRole('group', { name: 'Session' });
        expect(header).toHaveTextContent('Session not confirmed');
        expect(within(header).queryByRole('button', { name: 'Sign out' })).toBeNull();
        expect(link.csrf()).toBeUndefined();
      } finally {
        vi.unstubAllGlobals();
        cleanup();
      }
    }
  });

  it('only a 503 says a session is kept: another error status with a valid csrf member offers no Sign out and sets no token', async () => {
    const { fetchStub } = outageBackend({ csrfIn503: SYNTHETIC_CSRF, signOut: signedOutUnconfirmed, status: 500 });
    vi.stubGlobal('fetch', fetchStub);
    try {
      const link = renderControl();
      await settle();
      await settle();
      const header = screen.getByRole('group', { name: 'Session' });
      expect(header).toHaveTextContent('Session not confirmed');
      expect(within(header).queryByRole('button', { name: 'Sign out' })).toBeNull();
      expect(link.csrf()).toBeUndefined();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('waits longer for the session read than the time the backend gives a silent identity provider, so the late 503 still offers Sign out', async () => {
    // The backend's own value (CredentialValidation.PROVIDER_TIMEOUT), not a copy of it: raising it
    // to the shell's limit or above fails here. SignInIT measures the 503 itself against the
    // shell's limit, which also covers the work the backend does around the renewal.
    const BACKEND_PROVIDER_TIMEOUT_MS = backendProviderTimeoutMs();
    expect(SESSION_READ_TIMEOUT_MS).toBeGreaterThan(BACKEND_PROVIDER_TIMEOUT_MS);
    vi.useFakeTimers();
    // The backend answers once it has given up on the provider; an aborted read is never answered.
    const fetchStub = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          const answer = setTimeout(() => {
            resolve(
              new Response(JSON.stringify({ title: 'Service Unavailable', status: 503, csrf: SYNTHETIC_CSRF }), {
                status: 503,
                headers: { 'content-type': 'application/problem+json' },
              }),
            );
          }, BACKEND_PROVIDER_TIMEOUT_MS + 500);
          init?.signal?.addEventListener('abort', () => {
            clearTimeout(answer);
            reject(new DOMException('aborted', 'AbortError'));
          });
        }),
    );
    vi.stubGlobal('fetch', fetchStub);
    try {
      const link = renderControl();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(BACKEND_PROVIDER_TIMEOUT_MS);
      });
      expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Checking your session');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      const header = screen.getByRole('group', { name: 'Session' });
      expect(header).toHaveTextContent('Session not confirmed');
      expect(within(header).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
      expect(link.csrf()).toEqual(SYNTHETIC_CSRF);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('a sign-out refused for a stale token (403) reads the kept session again and retries once with the new token', async () => {
    const fresh = { headerName: SYNTHETIC_CSRF.headerName, token: 'synthetic-csrf-token-2' };
    const { seen, fetchStub } = outageBackend({
      csrfIn503: fresh,
      signOut: (csrf) =>
        csrf === fresh.token
          ? signedOutUnconfirmed()
          : new Response(JSON.stringify({ status: 403, title: 'Forbidden' }), { status: 403, headers: { 'content-type': 'application/problem+json' } }),
    });
    vi.stubGlobal('fetch', fetchStub);
    try {
      const link = renderControl();
      await settle();
      await settle();
      // The token the shell holds is no longer the session's.
      link.setCsrf({ headerName: SYNTHETIC_CSRF.headerName, token: 'stale-token' });
      await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
      await settle();
      await settle();
      expect(seen.signOuts).toEqual(['stale-token', fresh.token]);
      expect(seen.sessionReads).toBe(2);
      expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Signed out');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('a kept session is reported from a signed-out shell too (signed in in another tab during the outage)', async () => {
    vi.useFakeTimers();
    renderApp({ session: [ok(signedOut), { kind: 'error', status: 503, extension: SYNTHETIC_CSRF }] }, '/focus', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Signed out');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    vi.useRealTimers();
    const header = screen.getByRole('group', { name: 'Session' });
    expect(header).toHaveTextContent('Session not confirmed');
    expect(within(header).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeInTheDocument();
  });

  it('keeps the CSRF token over a failed read, so the sign-out carries it', async () => {
    let sessionReads = 0;
    const signOuts: (string | null)[] = [];
    const fetchStub = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url === '/api/session') {
        sessionReads += 1;
        return Promise.resolve(
          sessionReads === 1
            ? new Response(JSON.stringify(signedIn), { status: 200, headers: { 'content-type': 'application/json' } })
            : new Response(JSON.stringify({ status: 503, title: 'Service Unavailable' }), {
                status: 503,
                headers: { 'content-type': 'application/problem+json' },
              }),
        );
      }
      signOuts.push(new Headers(init?.headers).get(SYNTHETIC_CSRF.headerName));
      return Promise.resolve(
        new Response(JSON.stringify({ state: 'signed-out', identityProvider: 'unconfirmed' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });
    vi.stubGlobal('fetch', fetchStub);
    try {
      const link = createSessionLink();
      render(
        <ApiProvider config={{ apiPathPrefix: '/api' }} session={link}>
          <SessionProvider apiPathPrefix="/api" link={link}>
            <SessionControl />
          </SessionProvider>
        </ApiProvider>,
      );
      await settle();
      await settle();
      expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Signed in as Ada Synthetic');
      await act(async () => {
        window.dispatchEvent(new Event('focus'));
        await Promise.resolve();
      });
      await settle();
      await settle();
      expect(sessionReads).toBe(2);
      expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Session not confirmed');
      // The failed read said nothing about the session: its token is still the one to send.
      expect(link.csrf()).toEqual(SYNTHETIC_CSRF);
      await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
      await settle();
      await settle();
      expect(signOuts).toEqual([SYNTHETIC_CSRF.token]);
      expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Signed out');
      expect(link.csrf()).toBeUndefined();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe('the result of a sign-in is shown once', () => {
  it('is spent by the first answer and not shown for a later signed-out read', async () => {
    vi.useFakeTimers();
    // Returned with sign-in=failed although a session exists; it later ends behind failing reads.
    renderApp({ session: [ok(signedIn), { kind: 'error', status: 503 }, ok(signedOut)] }, '/focus?sign-in=failed', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.queryByRole('heading', { level: 2, name: 'Sign-in was not completed' })).toBeNull();
    expect(screen.getByRole('heading', { level: 2, name: 'Your session ended' })).toBeInTheDocument();
  });

  it('is still shown when the first read failed and the next one answers', async () => {
    vi.useFakeTimers();
    renderApp({ session: [{ kind: 'error', status: 503 }, ok(signedOut)] }, '/focus?sign-in=unavailable', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByRole('heading', { level: 2, name: 'The identity provider is unavailable' })).toBeInTheDocument();
  });
});

describe('the session is read only while somebody can see the page', () => {
  function setVisibility(value: 'visible' | 'hidden') {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
  }

  afterEach(() => {
    setVisibility('visible');
  });

  it('does not poll in a hidden tab, and reads at once when the tab is shown again', async () => {
    vi.useFakeTimers();
    const { client } = renderApp({ session: [ok(signedIn)] }, '/focus', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(client.sessionReads()).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(client.sessionReads()).toBe(3);

    setVisibility('hidden');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(10_000);
    });
    // Ten intervals passed unseen: the backend was not asked, so the session was not renewed.
    expect(client.sessionReads()).toBe(3);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(client.sessionReads()).toBe(4);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(client.sessionReads()).toBe(5);
  });
});

describe('session states in the shell (OM-02.01)', () => {
  it('signed out: the destination shows the signed-out state with a sign-in action and no protected content', async () => {
    const navigate = vi.fn();
    renderApp({ session: [ok(signedOut)] }, '/focus', { navigate });
    await settle();
    const main = screen.getByRole('main');
    expect(within(main).getByText('Signed out')).toBeInTheDocument();
    expect(within(main).getByRole('heading', { level: 2, name: 'You are signed out' })).toBeInTheDocument();
    expect(within(main).queryByText('No assigned work to show')).toBeNull();
    const header = screen.getByRole('group', { name: 'Session' });
    expect(within(header).getByText('Signed out')).toBeInTheDocument();
    await userEvent.setup().click(within(main).getByRole('button', { name: 'Sign in' }));
    await userEvent.setup().click(within(header).getByRole('button', { name: 'Sign in' }));
    expect(navigate.mock.calls).toEqual([['/api/session/sign-in'], ['/api/session/sign-in']]);
  });

  it('signed in: the person is named as text and the destination content is shown', async () => {
    renderApp({ session: [ok(signedIn)] });
    await settle();
    const header = screen.getByRole('group', { name: 'Session' });
    expect(header).toHaveTextContent('Signed in as Ada Synthetic');
    expect(within(header).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(within(header).queryByRole('button', { name: 'Sign in' })).toBeNull();
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
  });

  it('a display name is rendered as text, never as markup', async () => {
    const hostile = { ...signedIn, person: { principalId: 'p', displayName: '<img src=x onerror=alert(1)>' } } as SessionAnswer;
    renderApp({ session: [ok(hostile)] });
    await settle();
    const header = screen.getByRole('group', { name: 'Session' });
    expect(header).toHaveTextContent('<img src=x onerror=alert(1)>');
    expect(header.querySelector('img')).toBeNull();
  });

  it('loading is labelled and shows neither the signed-out state nor protected content', () => {
    const never: Pick<ApiClient, 'get'> = { get: () => new Promise(() => undefined) };
    window.history.replaceState(null, '', '/focus');
    const client: ApiClient = { get: never.get, post: <T,>() => Promise.resolve({ kind: 'error' } as ApiResult<T>) };
    render(<App config={{ apiPathPrefix: '/api' }} client={client} />);
    const main = screen.getByRole('main');
    expect(within(main).getByRole('heading', { level: 2, name: 'Checking your session' })).toBeInTheDocument();
    expect(within(main).queryByText('You are signed out')).toBeNull();
    expect(within(main).queryByText('No assigned work to show')).toBeNull();
    expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Checking your session…');
  });

  it('an unanswered session read becomes a problem state with a retry, never a permanent pending', async () => {
    vi.useFakeTimers();
    let aborted = false;
    let answerLater = false;
    const client: ApiClient = {
      get: <T,>(_path: string, options: { signal?: AbortSignal }) =>
        answerLater
          ? Promise.resolve({ kind: 'ok', value: signedIn } as ApiResult<T>)
          : new Promise<ApiResult<T>>((resolve) => {
              options.signal?.addEventListener('abort', () => {
                aborted = true;
                resolve({ kind: 'error' });
              });
            }),
      post: <T,>() => Promise.resolve({ kind: 'error' } as ApiResult<T>),
    };
    window.history.replaceState(null, '', '/focus');
    render(<App config={{ apiPathPrefix: '/api' }} client={client} sessionReadTimeoutMs={500} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    expect(aborted).toBe(true);
    const main = screen.getByRole('main');
    expect(within(main).getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Session' })).toHaveTextContent('Session not confirmed');
    answerLater = true;
    await act(async () => {
      within(main).getByRole('button', { name: 'Retry' }).click();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
  });

  it('a session answer of another shape or a failing endpoint is a problem, never signed in', async () => {
    renderApp({ session: [{ kind: 'error', status: 200 }] });
    await settle();
    expect(screen.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeInTheDocument();
    expect(screen.queryByText('No assigned work to show')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
  });

  it('expired: a later read that says signed out removes the content, says why and takes focus', async () => {
    vi.useFakeTimers();
    renderApp({ session: [ok(signedIn), ok(signedOut)] }, '/focus', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    const title = screen.getByRole('heading', { level: 2, name: 'Your session ended' });
    expect(title).toHaveFocus();
    expect(screen.queryByText('No assigned work to show')).toBeNull();
    expect(screen.getByRole('main')).toHaveTextContent('content that needs authorization was removed');
    expect(within(screen.getByRole('main')).getByRole('button', { name: 'Sign in again' })).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'Session' })).getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('a read that fails while signed in removes the content (fail closed)', async () => {
    vi.useFakeTimers();
    renderApp({ session: [ok(signedIn), { kind: 'error', status: 503 }] }, '/focus', { sessionPollIntervalMs: 1000 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.queryByText('No assigned work to show')).toBeNull();
    expect(screen.getByRole('heading', { level: 2, name: 'The session could not be checked' })).toBeInTheDocument();
  });

  it('re-reads the session when the window gets focus', async () => {
    const { client } = renderApp({ session: [ok(signedIn), ok(signedOut)] });
    await settle();
    expect(client.sessionReads()).toBe(1);
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(client.sessionReads()).toBe(2);
    expect(screen.getByRole('heading', { level: 2, name: 'Your session ended' })).toBeInTheDocument();
  });

  it('sign-in failed: a denied state, the parameter removed from the address, a way to try again', async () => {
    const navigate = vi.fn();
    renderApp({ session: [ok(signedOut)] }, '/focus?sign-in=failed', { navigate });
    await settle();
    const main = screen.getByRole('main');
    expect(within(main).getByText('Unavailable')).toBeInTheDocument();
    expect(within(main).getByRole('heading', { level: 2, name: 'Sign-in was not completed' })).toBeInTheDocument();
    expect(window.location.search).toBe('');
    expect(window.location.pathname).toBe('/focus');
    await userEvent.setup().click(within(main).getByRole('button', { name: 'Sign in again' }));
    expect(navigate).toHaveBeenCalledWith('/api/session/sign-in');
  });

  it('provider error: a distinct error state whose retry starts sign-in again', async () => {
    const navigate = vi.fn();
    renderApp({ session: [ok(signedOut)] }, '/?sign-in=unavailable', { navigate });
    await settle();
    const main = screen.getByRole('main');
    expect(within(main).getByText('Problem')).toBeInTheDocument();
    expect(within(main).getByRole('heading', { level: 2, name: 'The identity provider is unavailable' })).toBeInTheDocument();
    expect(within(main).queryByText('You are signed out')).toBeNull();
    expect(window.location.search).toBe('');
    await userEvent.setup().click(within(main).getByRole('button', { name: 'Retry sign-in' }));
    expect(navigate).toHaveBeenCalledWith('/api/session/sign-in');
  });

  it('a sign-in result in the address does not hide a person who is signed in', async () => {
    renderApp({ session: [ok(signedIn)] }, '/focus?sign-in=failed');
    await settle();
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    expect(window.location.search).toBe('');
  });

  it('sign out returns the shell to the signed-out state', async () => {
    const { client } = renderApp({ session: [ok(signedIn)] });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(client.signOutCalls()).toBe(1);
    expect(screen.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeInTheDocument();
    expect(screen.queryByText('No assigned work to show')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
    expect(screen.getByRole('main')).not.toHaveTextContent('could not confirm that the identity provider');
  });

  it('says so when the identity provider session could not be confirmed as ended', async () => {
    renderApp({ session: [ok(signedIn)], signOut: [{ kind: 'ok', value: { state: 'signed-out', identityProvider: 'unconfirmed' } }] });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(screen.getByRole('main')).toHaveTextContent('could not confirm that the identity provider ended its own');
  });

  it('a 401 on sign-out means there was no session: signed out, not expired', async () => {
    renderApp({ session: [ok(signedIn), ok(signedOut)], signOut: [{ kind: 'denied', status: 401 }] });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(screen.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeInTheDocument();
  });

  it('a 403 on sign-out re-reads the session once and retries once', async () => {
    const { client } = renderApp({
      session: [ok(signedIn)],
      signOut: [{ kind: 'denied', status: 403 }, { kind: 'ok', value: { state: 'signed-out', identityProvider: 'ended' } }],
    });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(client.signOutCalls()).toBe(2);
    expect(client.sessionReads()).toBe(2);
    expect(screen.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeInTheDocument();
  });

  it('a sign-out that is refused twice or fails is reported and nobody is shown as signed out', async () => {
    const { client } = renderApp({ session: [ok(signedIn)], signOut: [{ kind: 'denied', status: 403 }] });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(client.signOutCalls()).toBe(2);
    const header = screen.getByRole('group', { name: 'Session' });
    expect(within(header).getByRole('status')).toHaveTextContent('Sign-out could not be confirmed');
    expect(within(header).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
  });

  it('a 403 whose re-read says nobody is signed in ends as signed out', async () => {
    renderApp({ session: [ok(signedIn), ok(signedOut)], signOut: [{ kind: 'denied', status: 403 }] });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(screen.getByRole('heading', { level: 2, name: 'You are signed out' })).toBeInTheDocument();
  });

  it('an offline sign-out says it was not sent', async () => {
    renderApp({ session: [ok(signedIn)], signOut: [{ kind: 'offline' }] });
    await settle();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    await settle();
    expect(within(screen.getByRole('group', { name: 'Session' })).getByRole('status')).toHaveTextContent('sign-out was not sent');
  });

  it('Preferences and the public connection panel stay usable signed out', async () => {
    renderApp({ session: [ok(signedOut)] }, '/preferences');
    await settle();
    expect(screen.getByRole('heading', { level: 1, name: 'Preferences' })).toBeInTheDocument();
    expect(screen.queryByText('You are signed out')).toBeNull();
    renderApp({ session: [ok(signedOut)] }, '/');
    await settle();
    expect(screen.getAllByRole('region', { name: 'Workspace connection' }).length).toBeGreaterThan(0);
  });
});

describe('session with the real client', () => {
  function Probe() {
    const api = useApi();
    const { state } = useSession();
    return (
      <>
        <p data-testid="state">{state.kind}</p>
        <button
          type="button"
          onClick={() => {
            void api.get('/protected', { protected: true }, (body) => body);
          }}
        >
          Read protected
        </button>
      </>
    );
  }

  it('a 401 on a protected call makes the shell re-read the session, and the csrf token goes with it', async () => {
    let sessionReads = 0;
    const fetchStub = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url === '/api/session') {
        sessionReads += 1;
        return Promise.resolve(
          new Response(JSON.stringify(sessionReads === 1 ? signedIn : signedOut), { status: 200, headers: { 'content-type': 'application/json' } }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ status: 401, title: 'Unauthorized' }), { status: 401, headers: { 'content-type': 'application/problem+json' } }),
      );
    });
    vi.stubGlobal('fetch', fetchStub);
    try {
      const link = createSessionLink();
      render(
        <ApiProvider config={{ apiPathPrefix: '/api' }} session={link}>
          <SessionProvider apiPathPrefix="/api" link={link}>
            <Probe />
          </SessionProvider>
        </ApiProvider>,
      );
      await settle();
      await settle();
      expect(screen.getByTestId('state')).toHaveTextContent('signed-in');
      expect(link.csrf()).toEqual(signedIn.state === 'signed-in' ? signedIn.csrf : undefined);
      await userEvent.setup().click(screen.getByRole('button', { name: 'Read protected' }));
      await settle();
      await settle();
      expect(sessionReads).toBe(2);
      expect(screen.getByTestId('state')).toHaveTextContent('expired');
      expect(link.csrf()).toBeUndefined();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('refuses to be used without its provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow();
    spy.mockRestore();
  });
});
