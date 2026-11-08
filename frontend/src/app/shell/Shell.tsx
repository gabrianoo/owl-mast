import { useEffect, type ReactNode } from 'react';
import { APP_NAME, pageTitle, type Destination } from '../destinations.ts';
import { Link, useRouter } from '../router.tsx';
import { BrandMark } from './BrandMark.tsx';
import { PrimaryNavigation } from './PrimaryNavigation.tsx';
import { ScopeBar } from './ScopeBar.tsx';
import { SkipLink } from './SkipLink.tsx';

export const MAIN_ID = 'main';

export interface ShellProps {
  /** Heading of the current view; drives the document title and the focus target on navigation. */
  heading: string;
  destination: Destination | undefined;
  children: ReactNode;
}

/**
 * Workspace shell: skip link, brand (home link), primary navigation, scope bar and the main reading
 * area. On every in-app route change the document title updates and focus moves to the view's h1
 * (UX-DR40); the first paint leaves focus at the document start.
 */
export function Shell({ heading, destination, children }: ShellProps) {
  const { pathname, navigationCount } = useRouter();

  useEffect(() => {
    document.title = pageTitle(heading);
  }, [heading]);

  useEffect(() => {
    if (navigationCount === 0) return;
    const h1 = document.querySelector<HTMLElement>(`#${MAIN_ID} h1`);
    h1?.focus();
  }, [pathname, navigationCount]);

  return (
    <>
      <SkipLink targetId={MAIN_ID} />
      <div className="app">
        <header className="app__header">
          <Link to="/" className="brand" aria-label={`${APP_NAME} home`}>
            <BrandMark />
            <span>{APP_NAME}</span>
          </Link>
        </header>
        <div className="app__body">
          <PrimaryNavigation current={destination} />
          <main id={MAIN_ID} className="main" tabIndex={-1}>
            <ScopeBar />
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
