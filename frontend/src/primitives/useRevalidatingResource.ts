import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

/**
 * Stable "New updates" primitive (UX-DR40, accessibility floor): a resource is loaded once and then
 * re-checked on an interval; a changed value never replaces what the person is reading. It waits as
 * a pending update, announced once as a coalesced polite count, until they choose to apply it.
 *
 * Response ordering: every request carries its own token and only a response newer than the last
 * accepted one can take effect (latest issued wins). A response that invalidates the view (for the
 * connection panel: a denial) is applied at once, clears any pending update and, by being the newest
 * accepted response, makes every older outstanding request obsolete; the view can only come back
 * through a fresh load issued afterwards. Disabling the resource (offline) raises the invalidation
 * floor over every issued request, so outstanding responses and the pending update are discarded and
 * nothing received or held before the connection was lost can be shown until a load issued after
 * reconnecting succeeds.
 */
export interface RevalidatingResource<T> {
  /** The value currently shown, or undefined before the first load settles. */
  current: T | undefined;
  /** True until the first load settles. */
  loading: boolean;
  /** Number of coalesced pending updates (0 or 1: later changes replace the pending value). */
  pendingCount: number;
  /** Time the current value was received, for freshness labels. */
  receivedAt: Date | undefined;
  /** Shows the pending value; a no-op while disabled or when nothing applicable is pending. */
  applyPending: () => void;
  /** Forces a load now; the result still waits behind "New updates" unless nothing was shown yet. */
  refresh: () => void;
}

export interface RevalidatingOptions<T> {
  load: () => Promise<T>;
  intervalMs: number;
  isEqual: (a: T, b: T) => boolean;
  /** When false, no loads run and outstanding or pending values are discarded (for example offline). */
  enabled?: boolean;
  /** When true, the next value replaces the current one immediately (and clears the pending update). */
  applyImmediately?: (current: T, next: T) => boolean;
}

/**
 * Request ledger: tokens are issued in order; `accepted` is the newest token whose response took
 * effect; tokens at or below `floor` were invalidated before they settled. The floor is exposed as
 * an external store so render can read it without touching refs.
 */
interface RequestLedger {
  issue: () => number;
  /** Records the token as accepted when it is newer than everything accepted or invalidated so far. */
  accept: (token: number) => boolean;
  invalidateOutstanding: () => void;
  isApplicable: (token: number) => boolean;
  floor: () => number;
  subscribe: (listener: () => void) => () => void;
}

function createRequestLedger(): RequestLedger {
  let issued = 0;
  let accepted = 0;
  let floor = 0;
  const listeners = new Set<() => void>();
  return {
    issue: () => {
      issued += 1;
      return issued;
    },
    accept: (token) => {
      if (token <= floor || token <= accepted) return false;
      accepted = token;
      return true;
    },
    invalidateOutstanding: () => {
      floor = issued;
      listeners.forEach((listener) => {
        listener();
      });
    },
    isApplicable: (token) => token > floor,
    floor: () => floor,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export function useRevalidatingResource<T>(options: RevalidatingOptions<T>): RevalidatingResource<T> {
  const { intervalMs, enabled = true } = options;
  const [current, setCurrent] = useState<T | undefined>(undefined);
  const [receivedAt, setReceivedAt] = useState<Date | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  // The pending update remembers the token of the response that produced it; it is applicable only
  // while enabled and while that token is above the invalidation floor.
  const [pending, setPending] = useState<{ value: T; token: number } | undefined>(undefined);
  const [ledger] = useState(createRequestLedger);
  const floor = useSyncExternalStore(ledger.subscribe, ledger.floor);
  const currentRef = useRef<T | undefined>(undefined);
  const enabledRef = useRef(enabled);
  // Callbacks are read through a ref so a new inline function never restarts the schedule.
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  const runLoad = useCallback(async () => {
    if (!enabledRef.current) return;
    const token = ledger.issue();
    const { load, isEqual, applyImmediately } = optionsRef.current;
    let next: T;
    try {
      next = await load();
    } catch {
      return;
    }
    // Obsolete: disabled meanwhile, invalidated while in flight, or older than an accepted response.
    if (!enabledRef.current || !ledger.accept(token)) return;
    const shown = currentRef.current;
    if (shown === undefined || applyImmediately?.(shown, next)) {
      currentRef.current = next;
      setCurrent(next);
      setReceivedAt(new Date());
      setLoading(false);
      setPending(undefined);
      return;
    }
    if (isEqual(shown, next)) {
      setPending(undefined);
      return;
    }
    setPending({ value: next, token });
  }, [ledger]);

  useEffect(() => {
    enabledRef.current = enabled;
    if (!enabled) {
      // Going offline (or otherwise disabling): every outstanding request and the pending update
      // fall under the floor; only a load issued after re-enabling can show anything new.
      ledger.invalidateOutstanding();
      return undefined;
    }
    void runLoad();
    const timer = window.setInterval(() => {
      void runLoad();
    }, intervalMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs, runLoad, ledger]);

  const applyPending = useCallback(() => {
    if (!enabledRef.current) return;
    setPending((waiting) => {
      if (waiting !== undefined && ledger.isApplicable(waiting.token)) {
        currentRef.current = waiting.value;
        setCurrent(waiting.value);
        setReceivedAt(new Date());
      }
      return undefined;
    });
  }, [ledger]);

  const refresh = useCallback(() => {
    void runLoad();
  }, [runLoad]);

  return {
    current,
    loading,
    pendingCount: enabled && pending !== undefined && pending.token > floor ? 1 : 0,
    receivedAt,
    applyPending,
    refresh,
  };
}
