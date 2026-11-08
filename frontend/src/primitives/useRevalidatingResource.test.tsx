import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useRevalidatingResource, type RevalidatingOptions } from './useRevalidatingResource.ts';

type Probe = { kind: 'ok'; value: string } | { kind: 'denied' };

interface Deferred {
  resolve: (value: Probe) => void;
  reject: (error: Error) => void;
}

/** A load whose responses are settled by the test in any order, mirroring overlapping polls. */
function controlledLoad() {
  const requests: Deferred[] = [];
  const load = () =>
    new Promise<Probe>((resolve, reject) => {
      requests.push({ resolve, reject });
    });
  return { load, requests };
}

const options = (load: () => Promise<Probe>, enabled = true): RevalidatingOptions<Probe> => ({
  load,
  intervalMs: 1000,
  isEqual: (a, b) => a.kind === b.kind && (a.kind !== 'ok' || b.kind !== 'ok' || a.value === b.value),
  invalidates: (next) => next.kind === 'denied',
  enabled,
});

async function settle(action: () => void) {
  await act(async () => {
    action();
    await Promise.resolve();
  });
}

describe('useRevalidatingResource request ordering (AC3: a denial is never reversed by an older response)', () => {
  it('drops a stalled older response that arrives after a newer denial and keeps the pending count at zero', async () => {
    const { load, requests } = controlledLoad();
    const { result } = renderHook((props: RevalidatingOptions<Probe>) => useRevalidatingResource(props), {
      initialProps: options(load),
    });
    await settle(() => {
      requests[0]?.resolve({ kind: 'ok', value: 'v1' });
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v1' });

    // Poll A (token 2) stalls; poll B (token 3) is issued and answers denied first.
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      result.current.refresh();
    });
    expect(requests).toHaveLength(3);
    await settle(() => {
      requests[2]?.resolve({ kind: 'denied' });
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(0);

    // The stalled A finally succeeds with an older view: it must be ignored, not offered as an update.
    await settle(() => {
      requests[1]?.resolve({ kind: 'ok', value: 'v1' });
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(0);
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'denied' });

    // Only a fresh load issued after the denial can bring the view back.
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      requests[3]?.resolve({ kind: 'ok', value: 'v2' });
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v2' });
  });

  it('inverse order: an older success first, then the newer denial takes effect immediately and clears pending', async () => {
    const { load, requests } = controlledLoad();
    const { result } = renderHook((props: RevalidatingOptions<Probe>) => useRevalidatingResource(props), {
      initialProps: options(load),
    });
    await settle(() => {
      requests[0]?.resolve({ kind: 'ok', value: 'v1' });
    });
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      requests[1]?.resolve({ kind: 'ok', value: 'v2' });
    });
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      requests[2]?.resolve({ kind: 'denied' });
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(0);
  });

  it('latest issued wins among successes: an older late response never becomes the pending update', async () => {
    const { load, requests } = controlledLoad();
    const { result } = renderHook((props: RevalidatingOptions<Probe>) => useRevalidatingResource(props), {
      initialProps: options(load),
    });
    await settle(() => {
      requests[0]?.resolve({ kind: 'ok', value: 'v1' });
    });
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      requests[2]?.resolve({ kind: 'ok', value: 'v3' });
    });
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      requests[1]?.resolve({ kind: 'ok', value: 'v2' });
    });
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v3' });
  });
});

describe('useRevalidatingResource denial barrier (AC3: a denial invalidates every request issued before it)', () => {
  /** Shows v1, then issues A and B while v1 is shown; returns the controlled requests. */
  async function withTwoOutstanding() {
    const { load, requests } = controlledLoad();
    const hook = renderHook((props: RevalidatingOptions<Probe>) => useRevalidatingResource(props), {
      initialProps: options(load),
    });
    await settle(() => {
      requests[0]?.resolve({ kind: 'ok', value: 'v1' });
    });
    await settle(() => {
      hook.result.current.refresh(); // A (token 2)
    });
    await settle(() => {
      hook.result.current.refresh(); // B (token 3)
    });
    expect(requests).toHaveLength(3);
    return { ...hook, requests };
  }

  it('A issued, B issued, A denied, B succeeds late: nothing is restored and no update is offered', async () => {
    const { result, requests } = await withTwoOutstanding();
    await settle(() => {
      requests[1]?.resolve({ kind: 'denied' }); // A's denial arrives first
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(0);

    // B carries a higher token than A but was issued before the denial was accepted.
    await settle(() => {
      requests[2]?.resolve({ kind: 'ok', value: 'v2' });
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(0);
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(requests).toHaveLength(3);
  });

  it('a request issued after the denial can restore content', async () => {
    const { result, requests } = await withTwoOutstanding();
    await settle(() => {
      requests[1]?.resolve({ kind: 'denied' });
    });
    await settle(() => {
      requests[2]?.resolve({ kind: 'ok', value: 'v2' });
    });
    expect(result.current.pendingCount).toBe(0);

    await settle(() => {
      result.current.refresh(); // C (token 4), issued after the denial
    });
    await settle(() => {
      requests[3]?.resolve({ kind: 'ok', value: 'v3' });
    });
    expect(result.current.current).toEqual({ kind: 'denied' });
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v3' });
    expect(result.current.pendingCount).toBe(0);
  });
});

describe('useRevalidatingResource while disabled (AC3: nothing new is shown while offline)', () => {
  it('discards pending and outstanding values on disable, refuses applyPending, and only a post-reconnect load can show new values', async () => {
    const { load, requests } = controlledLoad();
    const { result, rerender } = renderHook((props: RevalidatingOptions<Probe>) => useRevalidatingResource(props), {
      initialProps: options(load),
    });
    await settle(() => {
      requests[0]?.resolve({ kind: 'ok', value: 'v1' });
    });
    await settle(() => {
      result.current.refresh();
    });
    await settle(() => {
      requests[1]?.resolve({ kind: 'ok', value: 'v2' });
    });
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      result.current.refresh();
    }); // outstanding when the connection drops

    rerender(options(load, false));
    expect(result.current.pendingCount).toBe(0);
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v1' });
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v1' });
    await settle(() => {
      requests[2]?.resolve({ kind: 'ok', value: 'v3' });
    });
    expect(result.current.pendingCount).toBe(0);
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v1' });
    await settle(() => {
      result.current.refresh();
    });
    expect(requests).toHaveLength(3);

    rerender(options(load, true));
    expect(requests).toHaveLength(4);
    await settle(() => {
      requests[3]?.resolve({ kind: 'ok', value: 'v4' });
    });
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v4' });
  });

  it('reports the value shown before a disconnect as stale until a post-reconnect load confirms or replaces it', async () => {
    const { load, requests } = controlledLoad();
    const { result, rerender } = renderHook((props: RevalidatingOptions<Probe>) => useRevalidatingResource(props), {
      initialProps: options(load),
    });
    await settle(() => {
      requests[0]?.resolve({ kind: 'ok', value: 'v1' });
    });
    expect(result.current.stale).toBe(false);

    rerender(options(load, false));
    expect(result.current.stale).toBe(true);
    rerender(options(load, true)); // post-reconnect check (token 2) still in flight
    expect(requests).toHaveLength(2);
    expect(result.current.stale).toBe(true);
    await settle(() => {
      requests[1]?.resolve({ kind: 'ok', value: 'v1' }); // equal answer confirms the shown value
    });
    expect(result.current.stale).toBe(false);
    expect(result.current.pendingCount).toBe(0);

    rerender(options(load, false));
    rerender(options(load, true));
    await settle(() => {
      requests[2]?.resolve({ kind: 'ok', value: 'v2' }); // changed answer waits behind New updates
    });
    expect(result.current.stale).toBe(true);
    expect(result.current.pendingCount).toBe(1);
    await settle(() => {
      result.current.applyPending();
    });
    expect(result.current.current).toEqual({ kind: 'ok', value: 'v2' });
    expect(result.current.stale).toBe(false);
  });
});
