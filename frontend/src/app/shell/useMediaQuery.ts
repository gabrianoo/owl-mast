import { useCallback, useSyncExternalStore } from 'react';

function supported(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function';
}

/** Subscribes to a CSS media query through useSyncExternalStore (no state writes in effects). */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!supported()) return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => {
        list.removeEventListener('change', onChange);
      };
    },
    [query],
  );
  const getSnapshot = useCallback(() => supported() && window.matchMedia(query).matches, [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
