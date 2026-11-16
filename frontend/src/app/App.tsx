import { useState } from 'react';
import { ApiProvider } from '../api/ApiProvider.tsx';
import type { ApiClient } from '../api/client.ts';
import type { RuntimeConfig } from '../api/config.ts';
import { createSessionLink } from '../api/session.ts';
import { DailyWork } from '../routes/DailyWork.tsx';
import { FirstUseDestination } from '../routes/FirstUseDestination.tsx';
import { Preferences } from '../routes/Preferences.tsx';
import { UNSUPPORTED_HEADING, Unsupported } from '../routes/Unsupported.tsx';
import { ConnectivityProvider } from '../state/connectivity.tsx';
import { ScopeProvider } from '../state/scope.tsx';
import { SessionProvider } from '../state/session.tsx';
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
  /** Test seam: shortens the session re-read interval. */
  sessionPollIntervalMs?: number;
  /** Test seam: bounds the session read. */
  sessionReadTimeoutMs?: number;
  /** Test seam: replaces the full-page navigation to the sign-in endpoint. */
  navigate?: (url: string) => void;
}

export function App({ config, client, pollIntervalMs, sessionPollIntervalMs, sessionReadTimeoutMs, navigate }: AppProps) {
  // One link per application: the client reads the CSRF token from it, the session state writes it.
  const [sessionLink] = useState(createSessionLink);
  return (
    <ThemeProvider>
      <ConnectivityProvider>
        <ScopeProvider>
          <ApiProvider config={config} session={sessionLink} {...(client ? { client } : {})}>
            <SessionProvider
              apiPathPrefix={config.apiPathPrefix}
              link={sessionLink}
              {...(sessionPollIntervalMs === undefined ? {} : { pollIntervalMs: sessionPollIntervalMs })}
              {...(sessionReadTimeoutMs === undefined ? {} : { readTimeoutMs: sessionReadTimeoutMs })}
              {...(navigate ? { navigate } : {})}
            >
              <RouterProvider>
                <Routes {...(pollIntervalMs === undefined ? {} : { pollIntervalMs })} />
              </RouterProvider>
            </SessionProvider>
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
