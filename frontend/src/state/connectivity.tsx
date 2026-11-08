import { createContext, useContext, useSyncExternalStore, type ReactNode } from 'react';

/**
 * Browser connectivity (EXPERIENCE.md state baseline): offline means no newly disclosed protected
 * content and no queued writes. `navigator.onLine` is advisory, so a failed request also moves the
 * affected content to its own error state; this provider only tracks the browser's signal.
 */
const ConnectivityContext = createContext<boolean>(true);

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

function getSnapshot(): boolean {
  return typeof navigator === 'undefined' || navigator.onLine;
}

export function ConnectivityProvider({ children, forceOnline }: { children: ReactNode; forceOnline?: boolean }) {
  const browserOnline = useSyncExternalStore(subscribe, getSnapshot, () => true);
  return <ConnectivityContext.Provider value={forceOnline ?? browserOnline}>{children}</ConnectivityContext.Provider>;
}

export function useOnline(): boolean {
  return useContext(ConnectivityContext);
}
