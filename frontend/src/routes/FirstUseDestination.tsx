import type { Destination } from '../app/destinations.ts';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { DestinationPage } from './DestinationPage.tsx';
import { SessionGate } from './SessionGate.tsx';

/**
 * A destination whose feature content arrives later: honest first-use state, no invented data. It
 * needs authorization, so only a signed-in person sees it (the public connection panel and
 * Preferences are not gated).
 */
export function FirstUseDestination({ destination }: { destination: Destination }) {
  return (
    <DestinationPage destination={destination}>
      <SessionGate subject={destination.label}>
        <StateMessage kind="empty" title={destination.firstUse.title} as="h2">
          <p>{destination.firstUse.body}</p>
        </StateMessage>
      </SessionGate>
    </DestinationPage>
  );
}
