import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from 'react';

/**
 * A small history-based router. The shell needs predictable title/focus handling on every route
 * change and a safe return location (EXPERIENCE.md interaction primitives); a full routing library
 * would add a qualification surface without adding behaviour the shell uses.
 */
export interface RouterState {
  pathname: string;
  /** Number of in-app navigations performed in this document (0 on first paint). */
  navigationCount: number;
  /** Depth of in-app history entries below the current one; 0 means "no safe in-app history". */
  depth: number;
  navigate: (to: string, options?: { replace?: boolean }) => void;
  /** Goes back to the previous in-app location, or to the fallback when there is none. */
  returnTo: (fallback: string) => void;
}

interface HistoryState {
  owlmastDepth?: number;
}

const RouterContext = createContext<RouterState | null>(null);

function currentDepth(): number {
  const state = window.history.state as HistoryState | null;
  return typeof state?.owlmastDepth === 'number' ? state.owlmastDepth : 0;
}

export function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith('/')) {
    return pathname.slice(0, -1);
  }
  return pathname || '/';
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [pathname, setPathname] = useState(() => normalizePath(window.location.pathname));
  const [depth, setDepth] = useState(currentDepth);
  const [navigationCount, setNavigationCount] = useState(0);

  useEffect(() => {
    const onPopState = () => {
      setPathname(normalizePath(window.location.pathname));
      setDepth(currentDepth());
      setNavigationCount((count) => count + 1);
    };
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('popstate', onPopState);
    };
  }, []);

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    const next = normalizePath(to);
    const nextDepth = options?.replace ? currentDepth() : currentDepth() + 1;
    const state: HistoryState = { owlmastDepth: nextDepth };
    if (options?.replace) {
      window.history.replaceState(state, '', next);
    } else {
      window.history.pushState(state, '', next);
    }
    setPathname(next);
    setDepth(nextDepth);
    setNavigationCount((count) => count + 1);
  }, []);

  const returnTo = useCallback(
    (fallback: string) => {
      if (currentDepth() > 0) {
        window.history.back();
      } else {
        navigate(fallback, { replace: true });
      }
    },
    [navigate],
  );

  const value = useMemo<RouterState>(
    () => ({ pathname, navigationCount, depth, navigate, returnTo }),
    [pathname, navigationCount, depth, navigate, returnTo],
  );
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter(): RouterState {
  const value = useContext(RouterContext);
  if (!value) {
    throw new Error('useRouter requires RouterProvider');
  }
  return value;
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string };

/** Same-document link: ordinary anchor semantics, in-app navigation on a plain left click. */
export function Link({ to, onClick, children, ...rest }: LinkProps) {
  const { navigate } = useRouter();
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
}
