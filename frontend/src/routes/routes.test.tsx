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

  it('removes shown content on a background denial without moving focus, and offers a working return', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([{ kind: 'ok', value: compatible }, { kind: 'denied', status: 403 }]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
      const scope = screen.getByRole('button', { name: 'Change scope' });
      scope.focus();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
      expect(screen.queryByText('0.1.0-SNAPSHOT')).toBeNull();
      const heading = screen.getByRole('heading', { level: 3, name: "This connection isn't available to this session" });
      // A background check is not a user action: focus stays where the person is working.
      expect(scope).toHaveFocus();
      expect(heading.closest('[role="status"]')).toHaveAttribute('aria-live', 'polite');
      expect(screen.getByText('Unavailable')).toBeInTheDocument();
      const back = screen.getByRole('link', { name: 'Return to Daily Work' });
      expect(back).toHaveAttribute('href', '/');
      await act(async () => {
        back.click();
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByRole('heading', { level: 1, name: 'Daily Work' })).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it('leaves focus at the document start when the first check is denied', async () => {
    const { client } = clientReturning([{ kind: 'denied', status: 401 }]);
    renderApp(client);
    expect(await screen.findByRole('heading', { level: 3, name: "This connection isn't available to this session" })).not.toHaveFocus();
    expect(document.body).toHaveFocus();
  });

  it('moves focus to the neutral heading when a denial removes the control that held it', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([
        { kind: 'ok', value: compatible },
        { kind: 'ok', value: { ...compatible, backendVersion: '0.2.0' } },
        { kind: 'denied', status: 403 },
      ]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      const show = screen.getByRole('button', { name: 'Show 1 new update' });
      act(() => {
        show.focus();
      });
      expect(show).toHaveFocus();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.queryByRole('button', { name: 'Show 1 new update' })).toBeNull();
      expect(screen.getByRole('heading', { level: 3, name: "This connection isn't available to this session" })).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not move focus on a denial after the person left the control (focus fell to the document)', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([
        { kind: 'ok', value: compatible },
        { kind: 'ok', value: { ...compatible, backendVersion: '0.2.0' } },
        { kind: 'denied', status: 403 },
      ]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      const show = screen.getByRole('button', { name: 'Show 1 new update' });
      await act(async () => {
        show.focus();
        // What a click on non-focusable page text does: focus leaves with no destination.
        show.blur();
        await Promise.resolve();
      });
      expect(document.body).toHaveFocus();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      const heading = screen.getByRole('heading', { level: 3, name: "This connection isn't available to this session" });
      expect(heading).not.toHaveFocus();
      expect(document.body).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it('still repairs focus when the window lost focus while the control held it (the control stays the active element)', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([
        { kind: 'ok', value: compatible },
        { kind: 'ok', value: { ...compatible, backendVersion: '0.2.0' } },
        { kind: 'denied', status: 403 },
      ]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      const show = screen.getByRole('button', { name: 'Show 1 new update' });
      await act(async () => {
        show.focus();
        // What switching to another window does: a focusout with no destination, and the control
        // remains document.activeElement.
        show.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
        await Promise.resolve();
      });
      expect(show).toHaveFocus();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByRole('heading', { level: 3, name: "This connection isn't available to this session" })).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ['a different major', { kind: 'ok', value: { ...compatible, apiContract: { major: 2, minor: 0 } } }, 'Incompatible frontend and backend'],
    ['no descriptor (404)', { kind: 'not-found' }, 'The backend did not publish a compatibility descriptor'],
  ] as [string, ApiResult<CompatibilityDescriptor>, string][])(
    'replaces a shown Compatible verdict at once when a re-check answers %s',
    async (_name, downgrade, title) => {
      vi.useFakeTimers();
      try {
        const { client } = clientReturning([{ kind: 'ok', value: compatible }, downgrade]);
        renderApp(client);
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000);
        });
        // Fail closed without a user action: no "New updates" step stands between a rollback and the verdict.
        expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
        expect(screen.getByText(title)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Show 1 new update/ })).toBeNull();
      } finally {
        vi.useRealTimers();
      }
    },
  );

  it.each([
    ['an error', { kind: 'error', status: 503 }, 'The backend could not be reached'],
    ['a dropped connection', { kind: 'offline' }, 'The connection dropped during the check'],
    ['a missing descriptor', { kind: 'not-found' }, 'The backend did not publish a compatibility descriptor'],
  ] as [string, ApiResult<CompatibilityDescriptor>, string][])(
    'does not pin %s: the next healthy answer replaces it without "New updates"',
    async (_name, first, title) => {
      vi.useFakeTimers();
      try {
        const { client } = clientReturning([first, { kind: 'ok', value: compatible }]);
        renderApp(client);
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        expect(screen.getByText(title)).toBeInTheDocument();
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000);
        });
        expect(screen.queryByText(title)).toBeNull();
        expect(screen.getByText('Compatible frontend and backend')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Show 1 new update/ })).toBeNull();
      } finally {
        vi.useRealTimers();
      }
    },
  );

  it('moves focus to the panel heading when a rollback removes the control that held it', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([
        { kind: 'ok', value: compatible },
        { kind: 'ok', value: { ...compatible, backendVersion: '0.2.0' } },
        { kind: 'ok', value: { ...compatible, apiContract: { major: 2, minor: 0 } } },
      ]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      act(() => {
        screen.getByRole('button', { name: 'Show 1 new update' }).focus();
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByText('Incompatible frontend and backend')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Show 1 new update' })).toBeNull();
      expect(screen.getByRole('heading', { level: 2, name: 'Workspace connection' })).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it('replaces a shown Compatible verdict at once when the API path stops answering with a descriptor', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([{ kind: 'ok', value: compatible }, { kind: 'error', status: 200 }]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
      expect(screen.getByText('The answer was not a compatibility descriptor')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Show 1 new update/ })).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('holds a recovery from Incompatible behind "New updates": only failing closed is automatic', async () => {
    vi.useFakeTimers();
    try {
      const { client } = clientReturning([
        { kind: 'ok', value: { ...compatible, apiContract: { major: 2, minor: 0 } } },
        { kind: 'ok', value: compatible },
      ]);
      renderApp(client);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByText('Incompatible frontend and backend')).toBeInTheDocument();
      expect(screen.queryByText('Compatible frontend and backend')).toBeNull();
      expect(screen.getByRole('button', { name: 'Show 1 new update' })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ['an error', { kind: 'error', status: 503 }],
    ['a dropped connection', { kind: 'offline' }],
    ['a denial', { kind: 'denied', status: 403 }],
  ] as [string, ApiResult<CompatibilityDescriptor>][])(
    'offline after %s shows one offline message and points at no values',
    async (_name, first) => {
      vi.useFakeTimers();
      try {
        const { client } = clientReturning([first]);
        renderApp(client);
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
        act(() => {
          window.dispatchEvent(new Event('offline'));
        });
        const panel = screen.getByRole('region', { name: 'Workspace connection' });
        expect(within(panel).getAllByText('Offline')).toHaveLength(1);
        expect(within(panel).getByText('You are offline')).toBeInTheDocument();
        expect(within(panel).queryByText('The connection dropped during the check')).toBeNull();
        expect(within(panel).queryByText(/values below/)).toBeNull();
        expect(within(panel).queryByText('Last known values')).toBeNull();
      } finally {
        vi.useRealTimers();
      }
    },
  );

  it('reports a successful answer that is not a descriptor as unverifiable, never as "status 200"', async () => {
    const { client } = clientReturning([{ kind: 'error', status: 200 }]);
    renderApp(client);
    expect(await screen.findByText('The answer was not a compatibility descriptor')).toBeInTheDocument();
    expect(screen.getByText(/treated as unsupported/)).toBeInTheDocument();
    expect(screen.queryByText(/status 200/)).toBeNull();
    expect(screen.queryByText('The backend could not be reached')).toBeNull();
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

  it('names the theme group once and ties the unsaved-change text to it', async () => {
    const user = userEvent.setup();
    const { client } = clientReturning([{ kind: 'ok', value: compatible }]);
    renderApp(client, '/preferences');
    expect(screen.queryByRole('radiogroup')).toBeNull();
    const group = screen.getByRole('group', { name: 'Theme' });
    expect(within(group).getAllByRole('radio')).toHaveLength(3);
    await user.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(group).toHaveAccessibleDescription(/Unsaved change: Dark/);
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
