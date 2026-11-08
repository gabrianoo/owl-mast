import { HOME } from '../app/destinations.ts';
import { Link, useRouter } from '../app/router.tsx';
import { StateMessage } from '../primitives/StateMessage.tsx';

export const UNSUPPORTED_HEADING = 'This destination isn’t available';

/**
 * Unknown or unsupported route: neutral copy (no echo of the requested address), the h1 receives
 * focus like any destination, and the return goes to the prior safe location or Daily Work.
 */
export function Unsupported() {
  const { depth, returnTo } = useRouter();
  return (
    <>
      <div className="page-header">
        <h1 tabIndex={-1}>{UNSUPPORTED_HEADING}</h1>
      </div>
      <StateMessage
        kind="unsupported"
        title="Owl Mast has no page at this address in this version"
        as="h2"
        action={
          depth > 0 ? (
            <button
              type="button"
              className="action action--secondary"
              onClick={() => {
                returnTo(HOME.path);
              }}
            >
              Back to where you were
            </button>
          ) : (
            <Link to={HOME.path} className="action action--secondary">
              Back to {HOME.label}
            </Link>
          )
        }
      >
        <p>Nothing was removed or hidden: the address is not a destination this shell knows.</p>
      </StateMessage>
    </>
  );
}
