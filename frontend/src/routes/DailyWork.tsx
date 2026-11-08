import { HOME } from '../app/destinations.ts';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { ConnectionPanel } from './ConnectionPanel.tsx';
import { DestinationPage } from './DestinationPage.tsx';

export function DailyWork({ pollIntervalMs }: { pollIntervalMs?: number }) {
  return (
    <DestinationPage destination={HOME}>
      <StateMessage kind="empty" title={HOME.firstUse.title} as="h2">
        <p>{HOME.firstUse.body}</p>
      </StateMessage>
      <ConnectionPanel {...(pollIntervalMs === undefined ? {} : { pollIntervalMs })} />
    </DestinationPage>
  );
}
