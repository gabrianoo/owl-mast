package com.aisquad.owlmast.fixtures.notes;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Stand-in for an external system with idempotent semantics: it counts how often each idempotency
 * key was received and applies the effect only the first time (AC2 duplicate effect recovery).
 */
public final class EffectStore {

  private final ConcurrentMap<String, AtomicInteger> received = new ConcurrentHashMap<>();

  /** Returns {@code true} when this call applied the effect, {@code false} on a duplicate. */
  public boolean apply(String idempotencyKey) {
    return received.computeIfAbsent(idempotencyKey, key -> new AtomicInteger()).incrementAndGet()
        == 1;
  }

  public int received(String idempotencyKey) {
    AtomicInteger count = received.get(idempotencyKey);
    return count == null ? 0 : count.get();
  }

  public int applied(String idempotencyKey) {
    return received.containsKey(idempotencyKey) ? 1 : 0;
  }

  public int distinctKeys() {
    return received.size();
  }

  public int totalReceived() {
    return received.values().stream().mapToInt(AtomicInteger::get).sum();
  }

  public void reset() {
    received.clear();
  }
}
