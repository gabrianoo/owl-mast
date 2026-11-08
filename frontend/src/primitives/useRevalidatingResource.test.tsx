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
  applyImmediately: (_current, next) => next.kind === 'denied',
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
});
