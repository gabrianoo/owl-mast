import { useEffect, useId, useRef, useState } from 'react';
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
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const navRef = useRef<HTMLElement | null>(null);
  const { pathname } = useRouter();
  const open = openForPath === pathname;
  const compact = !wide;
  const currentLabel = current?.label ?? 'Not a destination';

  // Escape dismisses the open compact menu wherever focus is. Focus returns to the control that
  // opened it only when it was inside the menu, so Escape never pulls focus from elsewhere.
  // An Escape that belongs to something else is left alone: one already handled, one that ends an
  // IME composition, and one pressed while a dialog is open (the dialog closes, the menu stays).
  useEffect(() => {
    if (!compact || !open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return;
      if (document.querySelector('dialog[open]') !== null) return;
      const focusInMenu = navRef.current?.contains(document.activeElement) ?? false;
      setOpenForPath(null);
      if (focusInMenu) toggleRef.current?.focus();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [compact, open]);

  return (
    <nav className="nav" aria-label="Primary navigation" ref={navRef}>
      {compact ? (
        <button
          type="button"
          ref={toggleRef}
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
              onClick={() => {
                // Activating the link of the page already shown changes no path, so close explicitly.
                setOpenForPath(null);
              }}
            >
              {destination.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
