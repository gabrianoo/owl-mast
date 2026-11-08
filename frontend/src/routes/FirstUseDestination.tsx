import type { Destination } from '../app/destinations.ts';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { DestinationPage } from './DestinationPage.tsx';

/** A destination whose feature content arrives later: honest first-use state, no invented data. */
export function FirstUseDestination({ destination }: { destination: Destination }) {
  return (
    <DestinationPage destination={destination}>
      <StateMessage kind="empty" title={destination.firstUse.title} as="h2">
        <p>{destination.firstUse.body}</p>
      </StateMessage>
    </DestinationPage>
  );
}
