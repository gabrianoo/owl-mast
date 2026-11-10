package com.aisquad.owlmast.platform.persistence;

import java.io.Serial;

/**
 * A scoped transaction tried to join an active transaction that is already bound to a different
 * {@code ScopeContext} (tenant or principal), or a transaction in which such a rejection happened
 * reached its end. Either way nothing commits under a confused scope (AD-4, AD-5).
 */
public final class IncompatibleScopeException extends IllegalStateException {

  @Serial private static final long serialVersionUID = 1L;

  private IncompatibleScopeException(String message) {
    super(message);
  }

  static IncompatibleScopeException requestedScopeDiffers() {
    return new IncompatibleScopeException(
        "Nested scoped transaction requested a ScopeContext that differs from the one bound to the"
            + " active transaction; a transaction carries exactly one tenant/principal scope");
  }

  static IncompatibleScopeException transactionPoisoned() {
    return new IncompatibleScopeException(
        "Scoped transaction cannot commit: a nested call with an incompatible ScopeContext was"
            + " rejected inside it, so the whole transaction is rolled back");
  }
}
