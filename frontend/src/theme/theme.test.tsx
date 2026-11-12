import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { readFrontendFile } from '../testing/planning.ts';
import { ThemeProvider, useTheme } from './ThemeProvider.tsx';
import {
  THEME_ATTRIBUTE,
  THEME_STORAGE_KEY,
  applyPreference,
  describePreference,
  readStoredPreference,
  resolveTheme,
  writeStoredPreference,
} from './themePreference.ts';

describe('theme preference (AC1: system theme plus explicit override)', () => {
  it('follows the device when nothing is stored or the stored value is unknown', () => {
    expect(readStoredPreference(undefined)).toBe('system');
    expect(readStoredPreference({ getItem: () => 'purple' })).toBe('system');
    expect(
      readStoredPreference({
        getItem: () => {
          throw new Error('blocked');
        },
      }),
    ).toBe('system');
    expect(readStoredPreference({ getItem: () => 'dark' })).toBe('dark');
  });

  it('resolves system to the device scheme and overrides to themselves', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
    expect(describePreference('system', 'dark')).toBe('Following your device (dark)');
  });

  it('expresses the override as data-owl-theme on the root and removes it for system', () => {
    const root = document.createElement('html');
    applyPreference('dark', root);
    expect(root.getAttribute(THEME_ATTRIBUTE)).toBe('dark');
    applyPreference('system', root);
    expect(root.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
  });

  it('persists overrides and clears storage for system', () => {
    writeStoredPreference(window.localStorage, 'light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    writeStoredPreference(window.localStorage, 'system');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});

function Probe() {
  const theme = useTheme();
  return (
    <button
      type="button"
      onClick={() => {
        void theme.save('dark').catch(() => undefined);
      }}
    >
      {theme.preference}/{theme.resolved}
    </button>
  );
}

describe('ThemeProvider', () => {
  it('applies a stored preference to the document on mount', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute(THEME_ATTRIBUTE)).toBe('dark');
    expect(screen.getByRole('button')).toHaveTextContent('dark/dark');
  });

  it('rejects the save and applies nothing when storage throws', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded');
    });
    let captured: unknown;
    function Saver() {
      const theme = useTheme();
      return (
        <button
          type="button"
          onClick={() => {
            theme.save('dark').catch((failure: unknown) => {
              captured = failure;
            });
          }}
        >
          save
        </button>
      );
    }
    render(
      <ThemeProvider>
        <Saver />
      </ThemeProvider>,
    );
    screen.getByRole('button').click();
    await vi.waitFor(() => {
      expect(captured).toBeInstanceOf(Error);
    });
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
    setItem.mockRestore();
  });
});

describe('pre-paint theme boot script (public/theme-boot.js)', () => {
  const source = readFrontendFile('public/theme-boot.js');
  const boot = () => {
    // The script is a classic, dependency-free IIFE served as a static file; run it as the browser does.
    // eslint-disable-next-line @typescript-eslint/no-implied-eval
    (new Function(source) as () => void)();
  };

  it('reads the same storage key and attribute as the theme provider', () => {
    expect(source).toContain(`getItem('${THEME_STORAGE_KEY}')`);
    expect(source).toContain(`setAttribute('${THEME_ATTRIBUTE}'`);
  });

  it('applies a saved explicit theme before React mounts and ignores anything else', () => {
    document.documentElement.removeAttribute(THEME_ATTRIBUTE);
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    boot();
    expect(document.documentElement.getAttribute(THEME_ATTRIBUTE)).toBe('dark');

    document.documentElement.removeAttribute(THEME_ATTRIBUTE);
    window.localStorage.setItem(THEME_STORAGE_KEY, 'purple');
    boot();
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);

    window.localStorage.removeItem(THEME_STORAGE_KEY);
    boot();
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
  });

  it('follows the device theme when storage is unavailable', () => {
    document.documentElement.removeAttribute(THEME_ATTRIBUTE);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(boot).not.toThrow();
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
  });
});
