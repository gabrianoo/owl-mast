import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { createApiClient, type ApiClient } from './client.ts';
import type { RuntimeConfig } from './config.ts';

const ApiContext = createContext<ApiClient | null>(null);

export function ApiProvider({ config, client, children }: { config: RuntimeConfig; client?: ApiClient; children: ReactNode }) {
  const value = useMemo(() => client ?? createApiClient({ apiPathPrefix: config.apiPathPrefix }), [client, config.apiPathPrefix]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  const value = useContext(ApiContext);
  if (!value) {
    throw new Error('useApi requires ApiProvider');
  }
  return value;
}
