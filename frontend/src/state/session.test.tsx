import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiClient, ApiResult } from '../api/client.ts';
import { ApiProvider, useApi } from '../api/ApiProvider.tsx';
import { createSessionLink, type SessionAnswer } from '../api/session.ts';
import { App } from '../app/App.tsx';
import { SYNTHETIC_PERSON, signedIn, signedOut, withSession, type SessionScript } from '../testing/session.ts';
import { SessionProvider, nextSessionState, useSession, type SessionState } from './session.tsx';

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
