/**
 * Theme preference (DESIGN.md delegated decision): follow the device theme initially and allow an
 * explicit user override. The override is expressed as `data-owl-theme` on <html>, which
 * tokens.css maps to the exact light/dark token sets.
 */
export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'owlmast.theme';
export const THEME_ATTRIBUTE = 'data-owl-theme';
export const DARK_SCHEME_QUERY = '(prefers-color-scheme: dark)';

export const THEME_PREFERENCES: readonly ThemePreference[] = ['system', 'light', 'dark'];

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark';
}

/** Reads the saved preference; anything unreadable or unknown means "system" (fail closed). */
export function readStoredPreference(storage: Pick<Storage, 'getItem'> | undefined): ThemePreference {
  try {
    const saved = storage?.getItem(THEME_STORAGE_KEY);
    return saved === 'light' || saved === 'dark' ? saved : 'system';
  } catch {
    return 'system';
  }
}

/** Persists the preference; throws when storage is unavailable so the caller can show a real failure. */
export function writeStoredPreference(storage: Pick<Storage, 'setItem' | 'removeItem'>, preference: ThemePreference): void {
  if (preference === 'system') {
    storage.removeItem(THEME_STORAGE_KEY);
  } else {
    storage.setItem(THEME_STORAGE_KEY, preference);
  }
}

export function applyPreference(preference: ThemePreference, root: Element): void {
  if (preference === 'system') {
    root.removeAttribute(THEME_ATTRIBUTE);
  } else {
    root.setAttribute(THEME_ATTRIBUTE, preference);
  }
}

export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): ResolvedTheme {
  if (preference === 'system') {
    return systemPrefersDark ? 'dark' : 'light';
  }
  return preference;
}

export function describePreference(preference: ThemePreference, resolved: ResolvedTheme): string {
  if (preference === 'system') {
    return `Following your device (${resolved})`;
  }
  return preference === 'dark' ? 'Dark' : 'Light';
}
