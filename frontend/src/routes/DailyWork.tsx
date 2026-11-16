import { HOME } from '../app/destinations.ts';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { ConnectionPanel } from './ConnectionPanel.tsx';
import { DestinationPage } from './DestinationPage.tsx';
import { SessionGate } from './SessionGate.tsx';

export function DailyWork({ pollIntervalMs }: { pollIntervalMs?: number }) {
  return (
    <DestinationPage destination={HOME}>
      <SessionGate subject={HOME.label}>
        <StateMessage kind="empty" title={HOME.firstUse.title} as="h2">
          <p>{HOME.firstUse.body}</p>
        </StateMessage>
      </SessionGate>
      <ConnectionPanel {...(pollIntervalMs === undefined ? {} : { pollIntervalMs })} />
    </DestinationPage>
  );
}
