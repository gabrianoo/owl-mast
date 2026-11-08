package com.aisquad.owlmast.jobs.api;

import java.util.Objects;

/**
 * What a handler knows about its external effect when it returns (AD-6: processing is at least
 * once). An item is marked {@code SUCCEEDED} only with an {@link Applied} outcome; {@link
 * Uncertain} leaves it in {@code OUTCOME_UNCERTAIN} awaiting reconciliation. The reference is an
 * identifier chosen by the handler (typically {@link WorkItem#idempotencyKey()} or the remote id),
 * never content or a secret.
 */
public sealed interface EffectOutcome permits EffectOutcome.Applied, EffectOutcome.Uncertain {

  String reference();

  static Applied applied(String reference) {
    return new Applied(reference);
  }

  static Uncertain uncertain(String reference) {
    return new Uncertain(reference);
  }

  /** The effect was applied exactly once (deduplicated by the idempotency key when repeated). */
  record Applied(String reference) implements EffectOutcome {
    public Applied {
      requireReference(reference);
    }
  }

  /** The handler cannot tell whether the effect happened; a reconciler must decide. */
  record Uncertain(String reference) implements EffectOutcome {
    public Uncertain {
      requireReference(reference);
    }
  }

  private static void requireReference(String reference) {
    Objects.requireNonNull(reference, "effect reference");
    if (reference.isBlank() || reference.length() > WorkItemContract.MAX_EFFECT_REFERENCE_LENGTH) {
      throw new IllegalArgumentException(
          "effect reference must be a non-blank identifier of at most "
              + WorkItemContract.MAX_EFFECT_REFERENCE_LENGTH
              + " characters");
    }
  }
}
