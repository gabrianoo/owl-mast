import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ApiClient, ApiResult } from '../api/client.ts';
import type { CompatibilityDescriptor } from '../api/compatibility.ts';
import { App } from '../app/App.tsx';
import { THEME_ATTRIBUTE, THEME_STORAGE_KEY } from '../theme/themePreference.ts';

const compatible: CompatibilityDescriptor = { service: 'owl-mast-backend', backendVersion: '0.1.0-SNAPSHOT', apiContract: { major: 1, minor: 0 } };

function clientReturning(results: ApiResult<CompatibilityDescriptor>[]): { client: ApiClient; calls: () => number } {
  let calls = 0;
  const client: ApiClient = {
    get: <T,>() => {
      calls += 1;
      const next = results.length > 1 ? results.shift() : results[0];
      return Promise.resolve((next ?? { kind: 'error' }) as ApiResult<T>);
    },
  };
  return { client, calls: () => calls };
}

function renderApp(client: ApiClient, path = '/', pollIntervalMs = 1000) {
  window.history.replaceState(null, '', path);
  return render(<App config={{ apiPathPrefix: '/api' }} client={client} pollIntervalMs={pollIntervalMs} />);
}

describe('Daily Work connection panel (AC3/AC4)', () => {
  it('shows labelled loading without numbers, then the compatible pair', async () => {
    let settle: (value: ApiResult<CompatibilityDescriptor>) => void = () => undefined;
    const client: ApiClient = {
      get: <T,>() =>
        new Promise<ApiResult<T>>((resolve) => {
          settle = resolve as (value: ApiResult<CompatibilityDescriptor>) => void;
        }),
    };
    renderApp(client);
    const panel = screen.getByRole('region', { name: 'Workspace connection' });
    expect(within(panel).getByText('Loading')).toBeInTheDocument();
    expect(within(panel).getByText('Checking the backend connection')).toBeInTheDocument();
    expect(within(panel).queryByText(/\d\.\d/)).toBeNull();
    await act(async () => {
      settle({ kind: 'ok', value: compatible });
      await Promise.resolve();
    });
    expect(within(panel).getByText('Compatible frontend and backend')).toBeInTheDocument();
    expect(within(panel).getByText('0.1.0-SNAPSHOT')).toBeInTheDocument();
    expect(within(panel).getByText('1.0')).toBeInTheDocument();
    expect(within(panel).getByText(/Checked at/)).toBeInTheDocument();
  });

  it('marks an incompatible pair unsupported, naming both contracts', async () => {
    const { client } = clientReturning([{ kind: 'ok', value: { ...compatible, apiContract: { major: 2, minor: 0 } } }]);
    renderApp(client);
    expect(await screen.findByText('Incompatible frontend and backend')).toBeInTheDocument();
    expect(screen.getByText(/supports API contract 1\.x.*publishes 2\.0/)).toBeInTheDocument();
    expect(screen.getByText('Unsupported')).toBeInTheDocument();
  });

  it('fails closed when the backend publishes no descriptor', async () => {
    const { client } = clientReturning([{ kind: 'not-found' }]);
    renderApp(client);
    expect(await screen.findByText('The backend did not publish a compatibility descriptor')).toBeInTheDocument();
    expect(screen.getByText(/treated as unsupported/)).toBeInTheDocument();
  });

  it('shows a distinct error without inventing values', async () => {
    const { client } = clientReturning([{ kind: 'error', status: 503 }]);
    renderApp(client);
    expect(await screen.findByText('The backend could not be reached')).toBeInTheDocument();
    expect(screen.getByText(/status 503/)).toBeInTheDocument();
    expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
  });

  it('removes shown content and focuses the neutral heading when access is denied on a re-check', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([{ kind: 'ok', value: compatible }, { kind: 'denied', status: 403 }]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
      expect(screen.queryByText('0.1.0-SNAPSHOT')).toBeNull();
      const heading = screen.getByRole('heading', { level: 3, name: "This connection isn't available to this session" });
      expect(heading).toHaveFocus();
      expect(screen.getByText('Unavailable')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('while offline requests nothing, shows the offline state and labels earlier values stale; reconnecting re-checks', async () => {
    vi.useFakeTimers();
    try {
      const { client, calls } = clientReturning([{ kind: 'ok', value: compatible }]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
      const before = calls();
      vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
      act(() => {
        window.dispatchEvent(new Event('offline'));
      });
      expect(screen.getByText('You are offline')).toBeInTheDocument();
      expect(screen.getByText('Last known values')).toBeInTheDocument();
      expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      expect(calls()).toBe(before);
      vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true);
      await act(async () => {
        window.dispatchEvent(new Event('online'));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(calls()).toBeGreaterThan(before);
      expect(screen.queryByText('You are offline')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('going offline discards a waiting update and a late response; only a post-reconnect check can offer one', async () => {
    vi.useFakeTimers();
    try {
      let answer: () => void = () => undefined;
      const results: ApiResult<CompatibilityDescriptor>[] = [
        { kind: 'ok', value: compatible },
        { kind: 'ok', value: { ...compatible, backendVersion: '0.2.0' } },
      ];
      let calls = 0;
      const client: ApiClient = {
        get: <T,>() => {
          calls += 1;
          const next = results.shift();
          if (next) return Promise.resolve(next as ApiResult<T>);
          // Third call stalls until the test answers it (after the connection dropped).
          return new Promise<ApiResult<T>>((resolve) => {
            answer = () => {
              resolve({ kind: 'ok', value: { ...compatible, backendVersion: '0.3.0' } } as ApiResult<T>);
            };
          });
        },
      };
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByText(/1 new update available/)).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000); // third poll issued and stalls
      });
      expect(calls).toBe(3);
      vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
      act(() => {
        window.dispatchEvent(new Event('offline'));
      });
      expect(screen.getByText('You are offline')).toBeInTheDocument();
      expect(screen.queryByText(/new update available/)).toBeNull();
      expect(screen.queryByRole('button', { name: /Show 1 new update/ })).toBeNull();
      await act(async () => {
        answer();
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.queryByText(/new update available/)).toBeNull();
      expect(screen.getByText('0.1.0-SNAPSHOT')).toBeInTheDocument();
      expect(screen.queryByText('0.3.0')).toBeNull();
      vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true);
      results.push({ kind: 'ok', value: { ...compatible, backendVersion: '0.4.0' } });
      await act(async () => {
        window.dispatchEvent(new Event('online'));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(calls).toBe(4);
      expect(screen.getByText(/1 new update available/)).toBeInTheDocument();
      await act(async () => {
        screen.getByRole('button', { name: 'Show 1 new update' }).click();
        await vi.advanceTimersByTimeAsync(50);
      });
      expect(screen.getByText('0.4.0')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps "Last known values" after reconnecting until the post-reconnect check succeeds', async () => {
    vi.useFakeTimers();
    try {
      let answer: () => void = () => undefined;
      let calls = 0;
      const client: ApiClient = {
        get: <T,>() => {
          calls += 1;
          if (calls === 1) return Promise.resolve({ kind: 'ok', value: compatible } as ApiResult<T>);
          // The post-reconnect check stalls until the test answers it.
          return new Promise<ApiResult<T>>((resolve) => {
            answer = () => {
              resolve({ kind: 'ok', value: compatible } as ApiResult<T>);
            };
          });
        },
      };
      renderApp(client, '/', 60_000);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
      vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
      act(() => {
        window.dispatchEvent(new Event('offline'));
      });
      expect(screen.getByText('Last known values')).toBeInTheDocument();

      vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true);
      await act(async () => {
        window.dispatchEvent(new Event('online'));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(calls).toBe(2);
      expect(screen.queryByText('You are offline')).toBeNull();
      expect(screen.getByText('Last known values')).toBeInTheDocument();
      expect(screen.queryByText('Compatible frontend and backend')).toBeNull();

      await act(async () => {
        answer();
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
      expect(screen.queryByText('Last known values')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('holds a changed backend version behind "New updates" until applied', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([
        { kind: 'ok', value: compatible },
        { kind: 'ok', value: { ...compatible, backendVersion: '0.2.0' } },
      ]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByText('0.1.0-SNAPSHOT')).toBeInTheDocument();
      expect(screen.getByText(/1 new update available/)).toBeInTheDocument();
      await act(async () => {
        screen.getByRole('button', { name: 'Show 1 new update' }).click();
        await vi.advanceTimersByTimeAsync(50);
      });
      expect(screen.getByText('0.2.0')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Workspace connection' })).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('Preferences (UX-DR25/27, AC1 override)', () => {
  it('saves the theme only on explicit Save and reports the real result', async () => {
    const user = userEvent.setup();
    const { client } = clientReturning([{ kind: 'ok', value: compatible }]);
    renderApp(client, '/preferences');
    expect(screen.getByRole('heading', { level: 1, name: 'Preferences' })).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(screen.getByText(/Unsaved change: Dark/)).toBeInTheDocument();
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Save theme' }));
    await vi.waitFor(() => {
      expect(screen.getByText('Theme saved: Dark.')).toBeInTheDocument();
    });
    expect(document.documentElement.getAttribute(THEME_ATTRIBUTE)).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(screen.getByText(/Current: Dark/)).toBeInTheDocument();
  });

  it('keeps the unsaved choice visible and shows a failure when storage refuses', async () => {
    const user = userEvent.setup();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded');
    });
    const { client } = clientReturning([{ kind: 'ok', value: compatible }]);
    renderApp(client, '/preferences');
    await user.click(screen.getByRole('radio', { name: 'Light' }));
    await user.click(screen.getByRole('button', { name: 'Save theme' }));
    await vi.waitFor(() => {
      expect(screen.getByText(/could not be saved/)).toBeInTheDocument();
    });
    expect(screen.getByRole('radio', { name: 'Light' })).toBeChecked();
    expect(screen.getByText(/Unsaved change: Light/)).toBeInTheDocument();
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
  });

  it('states that push is not offered instead of showing a notification setting', () => {
    const { client } = clientReturning([{ kind: 'ok', value: compatible }]);
    renderApp(client, '/preferences');
    expect(screen.getByText('Push notifications are not offered in this version')).toBeInTheDocument();
  });
});
