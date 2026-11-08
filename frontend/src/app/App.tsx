import { ApiProvider } from '../api/ApiProvider.tsx';
import type { ApiClient } from '../api/client.ts';
import type { RuntimeConfig } from '../api/config.ts';
import { DailyWork } from '../routes/DailyWork.tsx';
import { FirstUseDestination } from '../routes/FirstUseDestination.tsx';
import { Preferences } from '../routes/Preferences.tsx';
import { UNSUPPORTED_HEADING, Unsupported } from '../routes/Unsupported.tsx';
import { ConnectivityProvider } from '../state/connectivity.tsx';
import { ScopeProvider } from '../state/scope.tsx';
import { ThemeProvider } from '../theme/ThemeProvider.tsx';
import { findDestination } from './destinations.ts';
import { RouterProvider, useRouter } from './router.tsx';
import { Shell } from './shell/Shell.tsx';

export interface AppProps {
  config: RuntimeConfig;
  /** Test seam: a prepared client replaces the one built from the config. */
  client?: ApiClient;
  /** Test seam: shortens the connection re-check interval. */
  pollIntervalMs?: number;
}

export function App({ config, client, pollIntervalMs }: AppProps) {
  return (
    <ThemeProvider>
      <ConnectivityProvider>
        <ScopeProvider>
          <ApiProvider config={config} {...(client ? { client } : {})}>
            <RouterProvider>
              <Routes {...(pollIntervalMs === undefined ? {} : { pollIntervalMs })} />
            </RouterProvider>
          </ApiProvider>
        </ScopeProvider>
      </ConnectivityProvider>
    </ThemeProvider>
  );
}

function Routes({ pollIntervalMs }: { pollIntervalMs?: number }) {
  const { pathname } = useRouter();
  const destination = findDestination(pathname);
  if (!destination) {
    return (
      <Shell heading={UNSUPPORTED_HEADING} destination={undefined}>
        <Unsupported />
      </Shell>
    );
  }
  let view;
  switch (destination.id) {
    case 'daily-work':
      view = <DailyWork {...(pollIntervalMs === undefined ? {} : { pollIntervalMs })} />;
      break;
    case 'preferences':
      view = <Preferences />;
      break;
    default:
      view = <FirstUseDestination destination={destination} />;
  }
  return (
    <Shell heading={destination.heading} destination={destination}>
      {view}
    </Shell>
  );
}
