import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

/**
 * Stable "New updates" primitive (UX-DR40, accessibility floor): a resource is loaded once and then
 * re-checked on an interval; a changed value never replaces what the person is reading. It waits as
 * a pending update, announced once as a coalesced polite count, until they choose to apply it.
 *
 * Response ordering: every request carries its own token and only a response newer than the last
 * accepted one can take effect (latest issued wins). A response that invalidates the view (for the
 * connection panel: a denial) is applied at once, clears any pending update and raises the
 * invalidation floor over every request issued before it was accepted, older or newer than itself:
 * a request already in flight when the denial arrived was sent without knowing about it, so its
 * success can never restore the view. Only a load issued after the denial can. Disabling the
 * resource (offline) raises the same floor, so outstanding responses and the pending update are
 * discarded and nothing received or held before the connection was lost can be shown until a load
 * issued after reconnecting succeeds. The value received before the connection was lost is reported
 * `stale` until a later load confirms it (an equal answer) or replaces it.
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
  /**
   * True while the value shown was received before the last invalidation (going offline) and no load
   * issued since has confirmed it with an equal answer or replaced it.
   */
  stale: boolean;
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
  /**
   * When true, the response invalidates the view (for example a denial): it replaces the current
   * value immediately, clears the pending update and invalidates every request issued before it was
   * accepted, so only a load issued afterwards can show anything else.
   */
  invalidates?: (next: T) => boolean;
}

/**
 * Request ledger: tokens are issued in order; `accepted` is the newest token whose response took
 * effect; tokens at or below `floor` were invalidated before they settled. The floor is exposed as
 * an external store so render can read it without touching refs.
 */
interface RequestLedger {
  issue: () => number;
  /**
   * Records the token as accepted when it is newer than everything accepted or invalidated so far.
   * An invalidating acceptance also raises the floor to every token issued until now.
   */
  accept: (token: number, invalidating: boolean) => boolean;
  /** Disabling (offline): raises the floor and marks everything received so far as unconfirmed. */
  invalidateOutstanding: () => void;
  isApplicable: (token: number) => boolean;
  floor: () => number;
  /** Tokens at or below this were issued before the last disable; their values are stale. */
  disconnectFloor: () => number;
  subscribe: (listener: () => void) => () => void;
}

function createRequestLedger(): RequestLedger {
  let issued = 0;
  let accepted = 0;
  let floor = 0;
  let disconnectFloor = 0;
  const listeners = new Set<() => void>();
  const raiseFloor = () => {
    floor = issued;
    listeners.forEach((listener) => {
      listener();
    });
  };
  return {
    issue: () => {
      issued += 1;
      return issued;
    },
    accept: (token, invalidating) => {
      if (token <= floor || token <= accepted) return false;
      accepted = token;
      if (invalidating) raiseFloor();
      return true;
    },
    invalidateOutstanding: () => {
      disconnectFloor = issued;
      raiseFloor();
    },
    isApplicable: (token) => token > floor,
    floor: () => floor,
    disconnectFloor: () => disconnectFloor,
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
  // Token of the response that produced (or last confirmed) the shown value; at or under the
  // disconnect floor it was received before the connection was lost and is stale.
  const [shownToken, setShownToken] = useState(0);
  const [ledger] = useState(createRequestLedger);
  const floor = useSyncExternalStore(ledger.subscribe, ledger.floor);
  const disconnectFloor = useSyncExternalStore(ledger.subscribe, ledger.disconnectFloor);
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
    const { load, isEqual, invalidates } = optionsRef.current;
    let next: T;
    try {
      next = await load();
    } catch {
      return;
    }
    if (!enabledRef.current) return;
    const invalidating = invalidates?.(next) ?? false;
    // Obsolete: invalidated while in flight (offline, or a denial accepted after it was issued) or
    // older than an accepted response.
    if (!ledger.accept(token, invalidating)) return;
    const shown = currentRef.current;
    if (shown === undefined || invalidating) {
      currentRef.current = next;
      setCurrent(next);
      setShownToken(token);
      setReceivedAt(new Date());
      setLoading(false);
      setPending(undefined);
      return;
    }
    if (isEqual(shown, next)) {
      // A fresh answer equal to what is shown confirms it (clears a stale label after reconnecting).
      setShownToken(token);
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
        setShownToken(waiting.token);
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
    stale: current !== undefined && shownToken <= disconnectFloor,
    applyPending,
    refresh,
  };
}
