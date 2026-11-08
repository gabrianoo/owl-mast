import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Stable "New updates" primitive (UX-DR40, accessibility floor): a resource is loaded once and then
 * re-checked on an interval; a changed value never replaces what the person is reading. It waits as
 * a pending update, announced once as a coalesced polite count, until they choose to apply it.
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
  applyPending: () => void;
  /** Forces a load now; the result still waits behind "New updates" unless nothing was shown yet. */
  refresh: () => void;
}

export interface RevalidatingOptions<T> {
  load: () => Promise<T>;
  intervalMs: number;
  isEqual: (a: T, b: T) => boolean;
  /** When false, no loads run (for example while offline). */
  enabled?: boolean;
  /** When true, the next successful load replaces the current value immediately instead of pending. */
  applyImmediately?: (current: T, next: T) => boolean;
}

export function useRevalidatingResource<T>(options: RevalidatingOptions<T>): RevalidatingResource<T> {
  const { intervalMs, enabled = true } = options;
  const [current, setCurrent] = useState<T | undefined>(undefined);
  const [receivedAt, setReceivedAt] = useState<Date | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<T | undefined>(undefined);
  const currentRef = useRef<T | undefined>(undefined);
  const generation = useRef(0);
  // Callbacks are read through a ref so a new inline function never restarts the schedule.
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  const runLoad = useCallback(async () => {
    const myGeneration = generation.current;
    const { load, isEqual, applyImmediately } = optionsRef.current;
    let next: T;
    try {
      next = await load();
    } catch {
      return;
    }
    if (myGeneration !== generation.current) return;
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
    setPending(next);
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    generation.current += 1;
    void runLoad();
    const timer = window.setInterval(() => {
      void runLoad();
    }, intervalMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs, runLoad]);

  const applyPending = useCallback(() => {
    setPending((value) => {
      if (value !== undefined) {
        currentRef.current = value;
        setCurrent(value);
        setReceivedAt(new Date());
      }
      return undefined;
    });
  }, []);

  const refresh = useCallback(() => {
    void runLoad();
  }, [runLoad]);

  return {
    current,
    loading,
    pendingCount: pending === undefined ? 0 : 1,
    receivedAt,
    applyPending,
    refresh,
  };
}
