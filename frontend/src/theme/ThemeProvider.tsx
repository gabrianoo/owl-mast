import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  DARK_SCHEME_QUERY,
  applyPreference,
  readStoredPreference,
  resolveTheme,
  writeStoredPreference,
  type ResolvedTheme,
  type ThemePreference,
} from './themePreference.ts';

export interface ThemeState {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  /** Saves and applies the preference. Rejects with the storage failure; nothing is applied then. */
  save: (preference: ThemePreference) => Promise<void>;
}

const ThemeContext = createContext<ThemeState | null>(null);

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_SCHEME_QUERY).matches;
}

function storage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(() => readStoredPreference(storage()));
  const [prefersDark, setPrefersDark] = useState<boolean>(systemPrefersDark);

  useEffect(() => {
    applyPreference(preference, document.documentElement);
  }, [preference]);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia(DARK_SCHEME_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      setPrefersDark(event.matches);
    };
    query.addEventListener('change', onChange);
    return () => {
      query.removeEventListener('change', onChange);
    };
  }, []);

  const save = useCallback((next: ThemePreference): Promise<void> => {
    const target = storage();
    if (!target) {
      return Promise.reject(new Error('Browser storage is unavailable'));
    }
    try {
      writeStoredPreference(target, next);
    } catch (failure) {
      return Promise.reject(failure instanceof Error ? failure : new Error('Browser storage is unavailable'));
    }
    setPreference(next);
    return Promise.resolve();
  }, []);

  const value = useMemo<ThemeState>(
    () => ({ preference, resolved: resolveTheme(preference, prefersDark), save }),
    [preference, prefersDark, save],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error('useTheme requires ThemeProvider');
  }
  return value;
}
