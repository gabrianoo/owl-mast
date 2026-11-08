import { useId, useState } from 'react';
import { DESTINATIONS, type Destination } from '../destinations.ts';
import { Link, useRouter } from '../router.tsx';
import { useMediaQuery } from './useMediaQuery.ts';

export const WIDE_LAYOUT_QUERY = '(min-width: 1024px)';

/**
 * surface-navigation (UX-DR09): text labels with a blue selection indicator and `aria-current`;
 * below 1024px the same list sits behind a labelled menu button that names the current destination.
 * Navigation is read-only; it never hides a destination behind an icon.
 */
export function PrimaryNavigation({ current }: { current: Destination | undefined }) {
  const wide = useMediaQuery(WIDE_LAYOUT_QUERY);
  // The menu is open for exactly one path; navigating elsewhere closes it without an effect.
  const [openForPath, setOpenForPath] = useState<string | null>(null);
  const listId = useId();
  const { pathname } = useRouter();
  const open = openForPath === pathname;
  const compact = !wide;
  const currentLabel = current?.label ?? 'Not a destination';

  return (
    <nav className="nav" aria-label="Primary navigation">
      {compact ? (
        <button
          type="button"
          className="nav__toggle"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => {
            setOpenForPath(open ? null : pathname);
          }}
        >
          <span>Navigation</span>
          <span className="nav__current">{currentLabel}</span>
        </button>
      ) : null}
      <ul className="nav__list" id={listId} hidden={compact && !open}>
        {DESTINATIONS.map((destination) => (
          <li key={destination.id}>
            <Link
              to={destination.path}
              className="nav__link"
              aria-current={current?.id === destination.id ? 'page' : undefined}
            >
              {destination.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
