import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { createApiClient, type ApiClient } from './client.ts';
import type { RuntimeConfig } from './config.ts';
import type { SessionLink } from './session.ts';

const ApiContext = createContext<ApiClient | null>(null);

export function ApiProvider({
  config,
  client,
  session,
  children,
}: {
  config: RuntimeConfig;
  client?: ApiClient;
  /** Gives the client the CSRF token of the current session and hears about a 401 on a protected call. */
  session?: SessionLink;
  children: ReactNode;
}) {
  const value = useMemo(
    () => client ?? createApiClient({ apiPathPrefix: config.apiPathPrefix, ...(session ? { session } : {}) }),
    [client, config.apiPathPrefix, session],
  );
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  const value = useContext(ApiContext);
  if (!value) {
    throw new Error('useApi requires ApiProvider');
  }
  return value;
}
